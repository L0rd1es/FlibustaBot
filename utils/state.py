# state.py

import datetime
from config import DATA_EXPIRATION_TIME

user_ephemeral_mode = {}
author_mapping = {}
user_search_data = {}

async def cleanup_old_data():
    """Очищает устаревшие данные пользователей."""
    now = datetime.datetime.utcnow()
    expired_users = []

    for user_id, data in list(user_ephemeral_mode.items()):
        if (now - data["timestamp"]).total_seconds() > DATA_EXPIRATION_TIME:
            expired_users.append(user_id)

    for user_id in expired_users:
        user_ephemeral_mode.pop(user_id, None)
        user_search_data.pop(user_id, None)


def set_user_ephemeral_mode(user_id: int, mode: str):
    """
    Устанавливает временный режим поиска для пользователя.

    Args:
        user_id (int): Идентификатор пользователя.
        mode (str): Режим поиска.
    """
    user_ephemeral_mode[user_id] = mode

def get_user_ephemeral_mode(user_id: int) -> str | None:
    """
    Возвращает временный режим поиска для пользователя или None, если он не установлен.

    Args:
        user_id (int): Идентификатор пользователя.

    Returns:
        Optional[str]: Режим поиска или None.
    """
    return user_ephemeral_mode.get(user_id)

def clear_user_ephemeral_mode(user_id: int):
    """
    Очищает временный режим поиска для пользователя.

    Args:
        user_id (int): Идентификатор пользователя.
    """
    user_ephemeral_mode.pop(user_id, None)

def set_author_mapping(author_id: str, author_name: str):
    """
    Устанавливает соответствие между идентификатором автора и его именем.

    Args:
        author_id (str): Идентификатор автора.
        author_name (str): Имя автора.
    """
    author_mapping[author_id] = author_name

def get_author_mapping(author_id: str) -> str:
    """
    Возвращает имя автора по его идентификатору или 'Неизвестен', если соответствие отсутствует.

    Args:
        author_id (str): Идентификатор автора.

    Returns:
        str: Имя автора или "Неизвестен".
    """
    return author_mapping.get(author_id, "Неизвестен")

def set_user_search_data(user_id: int, records: list, pages: int):
    """
    Сохраняет данные поиска для пользователя.

    Args:
        user_id (int): Идентификатор пользователя.
        records (List[str]): Список записей результатов поиска.
        pages (int): Общее количество страниц.
    """
    user_search_data[user_id] = {"records": records, "page": 1, "pages": pages}

def get_user_search_data(user_id: int):
    """
    Возвращает данные поиска для пользователя или None, если данных нет.

    Args:
        user_id (int): Идентификатор пользователя.

    Returns:
        Optional[Dict[str, Any]]: Данные поиска или None.
    """
    return user_search_data.get(user_id)

def update_user_search_page(user_id: int, direction: str):
    """
    Обновляет текущую страницу поиска для пользователя.

    Args:
        user_id (int): Идентификатор пользователя.
        direction (str): Направление изменения страницы ('NEXT' для следующей, 'PREV' для предыдущей).
    """
    if user_id in user_search_data:
        info = user_search_data[user_id]
        if direction == "NEXT" and info["page"] < info["pages"]:
            info["page"] += 1
        elif direction == "PREV" and info["page"] > 1:
            info["page"] -= 1

def clear_user_search_data(user_id: int):
    """
    Очищает данные поиска для пользователя.

    Args:
        user_id (int): Идентификатор пользователя.
    """
    user_search_data.pop(user_id, None)
