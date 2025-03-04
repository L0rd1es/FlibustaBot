import logging
from typing import Optional, TypedDict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import SEARCH_RESULTS_PER_PAGE
from utils.state import get_user_search_data, update_user_search_page

logger = logging.getLogger(__name__)

class SearchState(TypedDict):
    records: list[str]
    page: int
    pages: int

def build_page_text(user_id: int) -> str:
    """
    Формирует текст для текущей страницы с результатами поиска.

    Args:
        user_id (int): Идентификатор пользователя.

    Returns:
        str: Текст страницы с информацией о номере страницы и записями результатов.
    """
    info: Optional[SearchState] = get_user_search_data(user_id)
    if not info:
        return "Данные поиска отсутствуют."

    records = info.get("records", [])
    current_page = info.get("page", 1)
    total_pages = info.get("pages", 1)

    if not records:
        return "Ничего не найдено."

    start_index = (current_page - 1) * SEARCH_RESULTS_PER_PAGE
    end_index = start_index + SEARCH_RESULTS_PER_PAGE
    chunk = records[start_index:end_index]

    lines = [f"Страница {current_page}/{total_pages}", ""]
    lines.extend(chunk)
    return "\n".join(lines)

def build_pagination_kb(user_id: int) -> Optional[InlineKeyboardMarkup]:
    """
    Создаёт кнопки навигации для пагинации.

    Args:
        user_id (int): Идентификатор пользователя.

    Returns:
        Optional[InlineKeyboardMarkup]: Разметка с кнопками или None, если пагинация не нужна.
    """
    info: Optional[SearchState] = get_user_search_data(user_id)
    if not info:
        return None

    current_page = info.get("page", 1)
    total_pages = info.get("pages", 1)

    if total_pages <= 1:
        return None

    btn_prev = (
        InlineKeyboardButton("« Назад", callback_data="pagination|PREV")
        if current_page > 1 else InlineKeyboardButton(" ", callback_data="no-op")
    )
    btn_next = (
        InlineKeyboardButton("Вперёд »", callback_data="pagination|NEXT")
        if current_page < total_pages else InlineKeyboardButton(" ", callback_data="no-op")
    )

    row = [
        btn_prev,
        InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="no-op"),
        btn_next,
    ]
    return InlineKeyboardMarkup([row])

async def pagination_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатия кнопок пагинации и обновляет сообщение с новыми результатами поиска.

    Args:
        update (Update): Обновление Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
    """
    if not update.callback_query:
        logger.error("Callback query отсутствует в update.")
        return

    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    search_data = get_user_search_data(user_id)
    if not search_data:
        await query.edit_message_text("Данные для пагинации отсутствуют.")
        return

    if data == "pagination|NEXT":
        update_user_search_page(user_id, "NEXT")
        logger.info(f"Пользователь {user_id} переключил на следующую страницу.")
    elif data == "pagination|PREV":
        update_user_search_page(user_id, "PREV")
        logger.info(f"Пользователь {user_id} переключил на предыдущую страницу.")
    else:
        logger.warning(f"Неизвестное действие пагинации: {data}")

    new_text = build_page_text(user_id)
    new_kb = build_pagination_kb(user_id)
    await query.edit_message_text(new_text, reply_markup=new_kb)
