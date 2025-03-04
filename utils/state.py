# state.py

user_ephemeral_mode = {}
author_mapping = {}
user_search_data = {}


def set_user_ephemeral_mode(user_id: int, mode: str):
    """Устанавливает временный режим поиска пользователя."""
    user_ephemeral_mode[user_id] = mode

def get_user_ephemeral_mode(user_id: int) -> str | None:
    """Возвращает временный режим поиска пользователя или None, если не установлен."""
    return user_ephemeral_mode.get(user_id)

def clear_user_ephemeral_mode(user_id: int):
    """Очищает временный режим поиска пользователя."""
    user_ephemeral_mode.pop(user_id, None)

def set_author_mapping(author_id: str, author_name: str):
    author_mapping[author_id] = author_name

def get_author_mapping(author_id: str) -> str:
    return author_mapping.get(author_id, "Неизвестен")

def set_user_search_data(user_id: int, records: list, pages: int):
    user_search_data[user_id] = {"records": records, "page": 1, "pages": pages}

def get_user_search_data(user_id: int):
    return user_search_data.get(user_id)

def update_user_search_page(user_id: int, direction: str):
    if user_id in user_search_data:
        info = user_search_data[user_id]
        if direction == "NEXT" and info["page"] < info["pages"]:
            info["page"] += 1
        elif direction == "PREV" and info["page"] > 1:
            info["page"] -= 1

def clear_user_search_data(user_id: int):
    user_search_data.pop(user_id, None)
