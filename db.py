# db.py

import sqlite3
from config import DB_PATH

INIT_SCRIPT = """
CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY,
    preferred_format TEXT,
    preferred_search_mode TEXT
);
"""

def init_db():
    """Инициализирует таблицы (если нет)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(INIT_SCRIPT)
    conn.commit()
    conn.close()

def get_user_settings(user_id: int) -> dict:
    """
    Возвращает словарь вида:
    {
      "preferred_format": str или None,
      "preferred_search_mode": str или None
    }
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT preferred_format, preferred_search_mode FROM user_settings WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
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

def set_user_settings(user_id: int, preferred_format: str = None, preferred_search_mode: str = None):
    """
    Записывает/обновляет настройки пользователя в базе.
    """
    # Сначала получим текущие, чтобы не затирать другие поля
    current = get_user_settings(user_id)
    pfmt = preferred_format or current["preferred_format"]
    pmode = preferred_search_mode or current["preferred_search_mode"]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO user_settings(user_id, preferred_format, preferred_search_mode)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            preferred_format=excluded.preferred_format,
            preferred_search_mode=excluded.preferred_search_mode
    """, (user_id, pfmt, pmode))
    conn.commit()
    conn.close()
