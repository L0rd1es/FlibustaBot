import aiosqlite
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict

from config import DB_PATH

logger = logging.getLogger(__name__)

INIT_SCRIPT = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    preferred_format TEXT,
    preferred_search_mode TEXT,
    preferred_book_naming TEXT DEFAULT 'title_author'
);
"""

# ========= Пул соединений =========

class DBPool:
    """
    Асинхронный пул соединений aiosqlite с динамическим масштабированием и
    защитой от «битых» коннекшнов.

    - Прогревает min_pool_size соединений.
    - При нехватке — создаёт новые до max_pool_size.
    - Перед выдачей — health-check (быстрый PRAGMA).
    - Возвращает в пул только «живые» соединения.
    """

    def __init__(
        self,
        db_path: str,
        min_pool_size: int = 1,
        max_pool_size: int = 2,           # SQLite лучше работает с небольшим пулом
        get_timeout: float = 5.0,
    ) -> None:
        self.db_path = db_path
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.get_timeout = get_timeout

        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=max_pool_size)
        self.current_connections: int = 0
        self._init_lock = asyncio.Lock()
        self.write_lock = asyncio.Lock()   # сериализуем запись (один писатель за раз)

    async def _create_connection(self) -> aiosqlite.Connection:
        """
        Создает новое соединение и настраивает полезные PRAGMA.
        """
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            # WAL — для параллельных читателей
            await conn.execute("PRAGMA journal_mode=WAL;")
            # Дадим SQLite подождать подольше вместо мгновенного 'database is locked'
            await conn.execute("PRAGMA busy_timeout=10000;")    # 10 сек
            # Компромисс скорость/надёжность
            await conn.execute("PRAGMA synchronous=NORMAL;")
            # Авточекапойнт, чтобы wal не разрастался
            await conn.execute("PRAGMA wal_autocheckpoint=1000;")
            await conn.commit()
        except Exception:
            # Не фатально, просто логируем
            logger.warning("Не удалось применить PRAGMA к SQLite-соединению", exc_info=True)
        return conn

    async def init_pool(self) -> None:
        """
        Прогрев пула: создаём минимально необходимое число соединений.
        Потокобезопасен.
        """
        async with self._init_lock:
            if self.current_connections >= self.min_pool_size:
                return
            for _ in range(self.min_pool_size):
                conn = await self._create_connection()
                await self._pool.put(conn)
                self.current_connections += 1
            logger.info("Инициализирован пул: %d соединений.", self.current_connections)

    async def _health_check(self, conn: aiosqlite.Connection) -> bool:
        """
        Быстрая проверка, что соединение «живое».
        """
        try:
            await conn.execute("PRAGMA user_version;")
            return True
        except Exception:
            return False

    async def get(self) -> aiosqlite.Connection:
        """
        Возвращает соединение из пула (с таймаутом). Если пул пуст и мы ниже max_pool_size —
        создаём новое соединение.
        """
        if self._pool.empty() and self.current_connections < self.max_pool_size:
            try:
                conn = await self._create_connection()
                self.current_connections += 1
                logger.info("Создано дополнительное соединение. Всего: %d.", self.current_connections)
                return conn
            except Exception:
                logger.exception("Ошибка при создании дополнительного соединения")
                raise

        try:
            conn = await asyncio.wait_for(self._pool.get(), timeout=self.get_timeout)
        except asyncio.TimeoutError:
            logger.error("Таймаут при ожидании соединения из пула")
            raise

        if not await self._health_check(conn):
            try:
                await conn.close()
            except Exception:
                pass
            self.current_connections -= 1
            logger.warning("Выдано «битое» соединение — закрыто. Осталось: %d.", self.current_connections)

            if self.current_connections < self.max_pool_size:
                new_conn = await self._create_connection()
                self.current_connections += 1
                logger.info("Заменили «битое» соединение. Всего: %d.", self.current_connections)
                return new_conn

            conn = await asyncio.wait_for(self._pool.get(), timeout=self.get_timeout)

        return conn

    async def put(self, conn: aiosqlite.Connection) -> None:
        """
        Возвращает соединение в пул. Закрытые/битые соединения — не возвращаем.
        """
        try:
            if not await self._health_check(conn):
                try:
                    await conn.close()
                except Exception:
                    pass
                self.current_connections -= 1
                logger.warning("Соединение не прошло health-check при возврате. Осталось: %d.", self.current_connections)
                return

            await self._pool.put(conn)
        except Exception:
            logger.exception("Ошибка при возврате соединения в пул")
            try:
                await conn.close()
            except Exception:
                pass
            self.current_connections -= 1
            raise

    async def close(self) -> None:
        """
        Закрывает все соединения пула.
        """
        while not self._pool.empty():
            conn = await self._pool.get()
            try:
                await conn.close()
            except Exception:
                pass
            self.current_connections -= 1
        logger.info("Пул закрыт. Текущее число соединений: %d.", self.current_connections)

    @asynccontextmanager
    async def connection(self):
        """
        Асинхронный контекстный менеджер:
            async with db_pool.connection() as conn:
                await conn.execute(...)
        Делает rollback при исключениях и всегда возвращает соединение в пул.
        """
        conn = await self.get()
        try:
            yield conn
        except Exception:
            try:
                await conn.rollback()
            except Exception:
                pass
            raise
        finally:
            await self.put(conn)


# Экземпляр пула
db_pool = DBPool(DB_PATH, min_pool_size=2, max_pool_size=2, get_timeout=5.0)


# ========= Инициализация БД =========

async def init_db() -> None:
    """
    Применяет миграции/DDL и прогревает пул.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript(INIT_SCRIPT)
            await db.commit()
        logger.info("База данных успешно инициализирована.")
    except Exception:
        logger.exception("Ошибка при инициализации базы данных")
        raise

    await db_pool.init_pool()


# ========= CRUD для user_settings =========

async def get_user_settings(user_id: int) -> Dict[str, Optional[str]]:
    """
    Возвращает словарь с настройками пользователя.
    Отсутствующие значения — None.
    """
    async with db_pool.connection() as conn:
        try:
            cursor = await conn.execute(
                """
                SELECT preferred_format, preferred_search_mode, preferred_book_naming
                FROM user_settings
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            await cursor.close()
            logger.debug("Настройки пользователя %s получены.", user_id)
        except Exception:
            logger.exception("Ошибка при SELECT настроек пользователя")
            raise

    if row:
        return {
            "preferred_format": row["preferred_format"],
            "preferred_search_mode": row["preferred_search_mode"],
            "preferred_book_naming": row["preferred_book_naming"],
        }
    return {"preferred_format": None, "preferred_search_mode": None, "preferred_book_naming": None}


async def set_user_settings(
    user_id: int,
    preferred_format: Optional[str] = None,
    preferred_search_mode: Optional[str] = None,
    preferred_book_naming: Optional[str] = None,
) -> None:
    """
    UPSERT без предварительного SELECT. Если параметр None — оставляем прежнее значение (COALESCE).
    """
    async with db_pool.connection() as conn:
        # Сериализуем операции записи
        async with db_pool.write_lock:
            try:
                await conn.execute(
                    """
                    INSERT INTO user_settings (user_id, preferred_format, preferred_search_mode, preferred_book_naming)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        preferred_format      = COALESCE(excluded.preferred_format,      user_settings.preferred_format),
                        preferred_search_mode = COALESCE(excluded.preferred_search_mode, user_settings.preferred_search_mode),
                        preferred_book_naming = COALESCE(excluded.preferred_book_naming, user_settings.preferred_book_naming)
                    """,
                    (user_id, preferred_format, preferred_search_mode, preferred_book_naming),
                )
                await conn.commit()
                logger.debug("Настройки пользователя %s обновлены.", user_id)
            except Exception:
                logger.exception("Ошибка при UPSERT настроек пользователя")
                raise
