import aiosqlite
import asyncio
import logging
from contextlib import asynccontextmanager
from config import DB_PATH

INIT_SCRIPT = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    preferred_format TEXT,
    preferred_search_mode TEXT,
    preferred_book_naming TEXT DEFAULT 'title_author'
);
"""

class DBPool:
    """
    Пул соединений для работы с базой данных с использованием aiosqlite.

    Пул поддерживает динамическое масштабирование: при инициализации создается min_pool_size соединений,
    а при необходимости пул может расширяться до max_pool_size.

    Attributes:
        db_path (str): Путь к базе данных.
        min_pool_size (int): Минимальное количество соединений в пуле.
        max_pool_size (int): Максимальное количество соединений в пуле.
        get_timeout (float): Время ожидания соединения перед выбрасыванием исключения.
        _pool (asyncio.Queue): Очередь, содержащая свободные соединения.
        current_connections (int): Текущее количество созданных соединений.
    """
    def __init__(self, db_path: str, min_pool_size: int = 1, max_pool_size: int = 10, get_timeout: float = 5.0):
        """
        Инициализирует пул соединений.

        Args:
            db_path (str): Путь к базе данных.
            min_pool_size (int, optional): Минимальное количество соединений, создаваемых при инициализации. По умолчанию 5.
            max_pool_size (int, optional): Максимальное количество соединений в пуле. По умолчанию 10.
            get_timeout (float, optional): Таймаут в секундах для ожидания соединения. По умолчанию 5.0 секунд.
        """
        self.db_path = db_path
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.get_timeout = get_timeout
        self._pool = asyncio.Queue(maxsize=max_pool_size)
        self.current_connections = 0

    async def init_pool(self):
        """
        Инициализирует пул, создавая минимальное количество соединений и помещая их в очередь.
        """
        for _ in range(self.min_pool_size):
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            await self._pool.put(conn)
            self.current_connections += 1
        logging.info(f"Инициализирован пул: {self.current_connections} соединений.")

    async def get(self):
        """
        Получает соединение из пула с учетом таймаута и динамического масштабирования.

        Если пул пуст, а созданных соединений меньше max_pool_size, создается новое соединение.
        Иначе ожидается освобождение соединения в течение get_timeout секунд.

        Returns:
            aiosqlite.Connection: Соединение с базой данных.

        Raises:
            asyncio.TimeoutError: Если соединение не освободилось в течение заданного времени.
        """
        if self._pool.empty() and self.current_connections < self.max_pool_size:
            try:
                conn = await aiosqlite.connect(self.db_path)
                conn.row_factory = aiosqlite.Row
                self.current_connections += 1
                logging.info(f"Создано дополнительное соединение. Всего: {self.current_connections}.")
                return conn
            except Exception as e:
                logging.exception("Ошибка при создании дополнительного соединения")
                raise
        try:
            conn = await asyncio.wait_for(self._pool.get(), timeout=self.get_timeout)
            return conn
        except asyncio.TimeoutError:
            logging.error("Таймаут при ожидании соединения из пула")
            raise

    async def put(self, conn):
        """
        Возвращает соединение обратно в пул.

        Args:
            conn (aiosqlite.Connection): Соединение для возврата.
        """
        try:
            await self._pool.put(conn)
        except Exception as e:
            logging.exception("Ошибка при возврате соединения в пул")
            raise

    async def close(self):
        """
        Закрывает все соединения в пуле.
        """
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()
        logging.info("Все соединения в пуле закрыты.")

    @asynccontextmanager
    async def connection(self):
        """
        Асинхронный контекстный менеджер для получения соединения из пула.

        Пример использования:
            async with db_pool.connection() as conn:
                await conn.execute(...)
        """
        conn = await self.get()
        try:
            yield conn
        finally:
            await self.put(conn)

db_pool = DBPool(DB_PATH, min_pool_size=5, max_pool_size=10, get_timeout=5.0)

async def init_db():
    """
    Инициализирует базу данных: создает необходимые таблицы и инициализирует пул соединений.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript(INIT_SCRIPT)
            await db.commit()
        logging.info("База данных успешно инициализирована.")
    except Exception as e:
        logging.exception("Ошибка при инициализации базы данных")
        raise

    await db_pool.init_pool()

async def get_user_settings(user_id: int) -> dict:
    """
    Получает настройки пользователя, используя соединение из пула.

    Args:
        user_id (int): Идентификатор пользователя.

    Returns:
        dict: Словарь с настройками пользователя. Если запись не найдена, возвращаются значения None.
    """
    async with db_pool.connection() as conn:
        try:
            cursor = await conn.execute(
                "SELECT preferred_format, preferred_search_mode, preferred_book_naming "
                "FROM user_settings WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            logging.info(f"Настройки для пользователя {user_id} получены.")
        except Exception as e:
            logging.exception("Ошибка при получении настроек пользователя")
            raise

    if row:
        return {
            "preferred_format": row["preferred_format"],
            "preferred_search_mode": row["preferred_search_mode"],
            "preferred_book_naming": row["preferred_book_naming"],
        }
    else:
        return {
            "preferred_format": None,
            "preferred_search_mode": None,
            "preferred_book_naming": None,
        }

async def set_user_settings(user_id: int, preferred_format: str = None, preferred_search_mode: str = None, preferred_book_naming: str = None):
    """
    Устанавливает или обновляет настройки пользователя, используя соединение из пула.

    Args:
        user_id (int): Идентификатор пользователя.
        preferred_format (str, optional): Предпочитаемый формат.
        preferred_search_mode (str, optional): Предпочитаемый режим поиска.
        preferred_book_naming (str, optional): Предпочитаемый способ именования книги.
    """
    current = await get_user_settings(user_id)
    pfmt = preferred_format or current["preferred_format"]
    pmode = preferred_search_mode or current["preferred_search_mode"]
    pbook_naming = preferred_book_naming or current["preferred_book_naming"]

    async with db_pool.connection() as conn:
        try:
            await conn.execute(
                """
                INSERT INTO user_settings(user_id, preferred_format, preferred_search_mode, preferred_book_naming)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_format = excluded.preferred_format,
                    preferred_search_mode = excluded.preferred_search_mode,
                    preferred_book_naming = excluded.preferred_book_naming
                """,
                (user_id, pfmt, pmode, pbook_naming)
            )
            await conn.commit()
            logging.info(f"Настройки для пользователя {user_id} установлены/обновлены.")
        except Exception as e:
            logging.exception("Ошибка при установке настроек пользователя")
            raise
