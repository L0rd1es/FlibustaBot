#author_books.py

import logging
import re
from telegram import Update
from telegram.ext import ContextTypes
from services.service import get_author_books
from config import SEARCH_RESULTS_PER_PAGE
from utils.chat_actions import set_typing_action
from utils.pagination import build_page_text, build_pagination_kb
from utils.state import get_author_mapping, set_user_search_data

logger = logging.getLogger(__name__)

async def author_books_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /author<ID> и показывает список книг автора."""
    await set_typing_action(update, context)
    
    text = update.message.text.strip()
    user_id = update.effective_user.id

    match = re.match(r"/author(\d+)$", text)
    if not match:
        await update.message.reply_text("Некорректная команда. Используйте формат: /author<ID>")
        return

    author_id = match.group(1)
    default_author = get_author_mapping(author_id)

    try:
        books = await get_author_books(author_id, default_author=default_author)
    except Exception as e:
        logger.error(f"Ошибка при получении книг автора {author_id}: {e}")
        await update.message.reply_text("Не удалось получить книги автора.")
        return

    if not books:
        await update.message.reply_text("У автора нет книг или он не найден.")
        return

    records = [
        f"{book.get('title', 'Без названия')}\n{book.get('author', 'Неизвестен')}\nСкачать: /download{book.get('id', 'N/A')}\n"
        for book in books
    ]

    total_pages = (len(records) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE

    set_user_search_data(user_id, records, total_pages)

    text_response = build_page_text(user_id)
    keyboard = build_pagination_kb(user_id)

    await update.message.reply_text(text_response, reply_markup=keyboard)