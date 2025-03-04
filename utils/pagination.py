#pagination.py

import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes
from config import SEARCH_RESULTS_PER_PAGE
from utils.state import get_user_search_data, update_user_search_page

logger = logging.getLogger(__name__)

def build_page_text(user_id: int) -> str:
    """Формирует текст для текущей страницы с результатами поиска."""
    info = get_user_search_data(user_id)

    if not info:
        return "Данные поиска отсутствуют."

    recs = info["records"]
    page = info["page"]
    pages = info["pages"]

    if not recs:
        return "Ничего не найдено."

    start_i = (page - 1) * SEARCH_RESULTS_PER_PAGE
    end_i = start_i + SEARCH_RESULTS_PER_PAGE
    chunk = recs[start_i:end_i]

    lines = [f"Страница {page}/{pages}", ""]
    lines.extend(chunk)
    return "\n".join(lines)

def build_pagination_kb(user_id: int):
    """Создаёт кнопки навигации для пагинации."""
    info = get_user_search_data(user_id)

    if not info:
        return None

    page = info["page"]
    pages = info["pages"]

    if pages <= 1:
        return None

    btn_prev = InlineKeyboardButton("« Назад", callback_data="pagination|PREV") if page > 1 else InlineKeyboardButton(" ", callback_data="no-op")
    btn_next = InlineKeyboardButton("Вперёд »", callback_data="pagination|NEXT") if page < pages else InlineKeyboardButton(" ", callback_data="no-op")

    row = [btn_prev, InlineKeyboardButton(f"{page}/{pages}", callback_data="no-op"), btn_next]
    return InlineKeyboardMarkup([row])

async def pagination_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия кнопок пагинации."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if not get_user_search_data(user_id):
        await query.edit_message_text("Данные для пагинации отсутствуют.")
        return

    if data == "pagination|NEXT":
        update_user_search_page(user_id, "NEXT")
    elif data == "pagination|PREV":
        update_user_search_page(user_id, "PREV")

    new_text = build_page_text(user_id)
    new_kb = build_pagination_kb(user_id)

    await query.edit_message_text(new_text, reply_markup=new_kb)