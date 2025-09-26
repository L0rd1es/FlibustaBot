# state.py

import datetime
import threading
from typing import Optional, Any, Dict, List
from config import DATA_EXPIRATION_TIME

# Глобальные структуры состояния
user_ephemeral_mode: Dict[int, Dict[str, Any]] = {}
author_mapping: Dict[str, str] = {}
user_search_data: Dict[int, Dict[str, Any]] = {}

# Рекурсивная блокировка для всех структур (не требует await и не ломает API)
_state_lock = threading.RLock()


async def cleanup_old_data():
    """Очищает устаревшие данные пользователей (по таймауту от timestamp)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    expired_users: List[int] = []

    # Берём снимок под локом
    with _state_lock:
        for user_id, data in list(user_ephemeral_mode.items()):
            ts: Optional[datetime.datetime] = data.get("timestamp")
            if ts and (now - ts).total_seconds() > DATA_EXPIRATION_TIME:
                expired_users.append(user_id)

        for user_id in expired_users:
            user_ephemeral_mode.pop(user_id, None)
            user_search_data.pop(user_id, None)


def set_user_ephemeral_mode(user_id: int, mode: str) -> None:
    """
    Устанавливает временный режим поиска для пользователя.
    Хранится как dict: {"mode": str, "timestamp": datetime}.
    """
    with _state_lock:
        user_ephemeral_mode[user_id] = {
            "mode": mode,
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
        }


def get_user_ephemeral_mode(user_id: int) -> Optional[str]:
    """
    Возвращает временный режим поиска для пользователя или None.
    """
    with _state_lock:
        data = user_ephemeral_mode.get(user_id)
        return data["mode"] if data else None


def clear_user_ephemeral_mode(user_id: int) -> None:
    """Очищает временный режим поиска для пользователя."""
    with _state_lock:
        user_ephemeral_mode.pop(user_id, None)


def set_author_mapping(author_id: str, author_name: str) -> None:
    """Устанавливает соответствие между ID автора и его именем."""
    with _state_lock:
        author_mapping[author_id] = author_name


def get_author_mapping(author_id: str) -> str:
    """Возвращает имя автора или 'Неизвестен'."""
    with _state_lock:
        return author_mapping.get(author_id, "Неизвестен")


def set_user_search_data(user_id: int, records: List[str], pages: int) -> None:
    """Сохраняет результаты поиска для пользователя."""
    with _state_lock:
        user_search_data[user_id] = {
            "records": records,
            "page": 1,
            "pages": pages,
        }


def get_user_search_data(user_id: int) -> Optional[Dict[str, Any]]:
    """Возвращает данные поиска пользователя или None (копию, чтобы снаружи не портили состояние)."""
    with _state_lock:
        data = user_search_data.get(user_id)
        return dict(data) if data else None


def update_user_search_page(user_id: int, direction: str) -> None:
    """Переключает страницу результатов поиска (NEXT или PREV)."""
    with _state_lock:
        info = user_search_data.get(user_id)
        if not info:
            return
        if direction == "NEXT" and info["page"] < info["pages"]:
            info["page"] += 1
        elif direction == "PREV" and info["page"] > 1:
            info["page"] -= 1


def clear_user_search_data(user_id: int) -> None:
    """Очищает данные поиска для пользователя."""
    with _state_lock:
        user_search_data.pop(user_id, None)
