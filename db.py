import aiosqlite
from config import DB_PATH

INIT_SCRIPT = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    preferred_format TEXT,
    preferred_search_mode TEXT
);
"""

async def init_db():
    """Асинхронная инициализация базы данных (создание таблиц, если нет)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(INIT_SCRIPT)
        await db.commit()

async def get_user_settings(user_id: int) -> dict:
    """
    Возвращает словарь вида:
    {
      "preferred_format": str или None,
      "preferred_search_mode": str или None
    }
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT preferred_format, preferred_search_mode FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
    if row:
        return {
            "preferred_format": row[0],
            "preferred_search_mode": row[1],
        }
    else:
        return {
            "preferred_format": None,
            "preferred_search_mode": None,
        }

async def set_user_settings(user_id: int, preferred_format: str = None, preferred_search_mode: str = None):
    """
    Асинхронно записывает/обновляет настройки пользователя в базе.
    """
    # Сначала получаем текущие настройки, чтобы не затирать другие поля
    current = await get_user_settings(user_id)
    pfmt = preferred_format or current["preferred_format"]
    pmode = preferred_search_mode or current["preferred_search_mode"]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_settings(user_id, preferred_format, preferred_search_mode)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                preferred_format = excluded.preferred_format,
                preferred_search_mode = excluded.preferred_search_mode
        """, (user_id, pfmt, pmode))
        await db.commit()
