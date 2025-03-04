import aiosqlite
import asyncio
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
    def __init__(self, db_path: str, pool_size: int = 5):
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool = asyncio.Queue(maxsize=pool_size)

    async def init_pool(self):
        for _ in range(self.pool_size):
            conn = await aiosqlite.connect(self.db_path)
            await self._pool.put(conn)

    async def get(self):
        return await self._pool.get()

    async def put(self, conn):
        await self._pool.put(conn)

    async def close(self):
        while not self._pool.empty():
            conn = await self._pool.get()
            await conn.close()

db_pool = DBPool(DB_PATH, pool_size=5)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(INIT_SCRIPT)
        await db.commit()
    await db_pool.init_pool()

async def get_user_settings(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT preferred_format, preferred_search_mode, preferred_book_naming FROM user_settings WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        await cursor.close()
    if row:
        return {
            "preferred_format": row[0],
            "preferred_search_mode": row[1],
            "preferred_book_naming": row[2],
        }
    else:
        return {
            "preferred_format": None,
            "preferred_search_mode": None,
            "preferred_book_naming": None,
        }

async def set_user_settings(user_id: int, preferred_format: str = None, preferred_search_mode: str = None, preferred_book_naming: str = None):
    current = await get_user_settings(user_id)
    pfmt = preferred_format or current["preferred_format"]
    pmode = preferred_search_mode or current["preferred_search_mode"]
    pbook_naming = preferred_book_naming or current["preferred_book_naming"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_settings(user_id, preferred_format, preferred_search_mode, preferred_book_naming)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                preferred_format = excluded.preferred_format,
                preferred_search_mode = excluded.preferred_search_mode,
                preferred_book_naming = excluded.preferred_book_naming
        """, (user_id, pfmt, pmode, pbook_naming))
        await db.commit()
