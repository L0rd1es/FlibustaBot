# handlers/message_handler.py

import logging
import re
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

from services.service import search_books_and_authors, get_book_details, download_book
from services.db import get_user_settings
from config import SEARCH_RESULTS_PER_PAGE
from utils.chat_actions import set_typing_action, run_with_periodic_action
from utils.pagination import build_page_text, build_pagination_kb
from handlers.author_handler import author_books_command
from handlers.book_handler import send_book_details_message
from utils.state import (
    set_author_mapping,
    set_user_search_data,
    get_user_ephemeral_mode,
    clear_user_ephemeral_mode,
)
from utils.utils import send_or_edit_message

logger = logging.getLogger(__name__)


async def _safe_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Пытается отправить текст пользователю вне зависимости от наличия message."""
    try:
        if update.message is not None:
            await update.message.reply_text(text)
            return
        if update.effective_chat is not None:
            await context.bot.send_message(update.effective_chat.id, text)
            return
        if update.effective_user is not None:
            await context.bot.send_message(update.effective_user.id, text)
    except Exception as e:
        logger.warning("Не удалось отправить сообщение пользователю: %s", e)


async def handle_download_command(book_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Загрузка книги по ID: учитывает preferred_format, шлёт карточку + файл (если доступен)."""
    if not book_id.isdigit():
        await _safe_reply_text(update, context, "Некорректный ID.")
        return

    try:
        logger.info("Получение деталей книги book_id=%s", book_id)
        details = await run_with_periodic_action(
            get_book_details(book_id),
            update,
            context,
            action=ChatAction.TYPING,
            interval=4,
        )
    except Exception:
        logger.exception("Ошибка при получении деталей книги")
        await _safe_reply_text(update, context, "Не удалось получить книгу.")
        return

    user = update.effective_user
    user_id = user.id if user else 0
    settings = await get_user_settings(user_id)
    preferred_format = settings.get("preferred_format")

    # если формат задан и доступен — качаем файл
    if preferred_format and preferred_format in details.get("formats", []):
        try:
            logger.info("Скачивание книги %s в формате %s", book_id, preferred_format)
            file_data = await run_with_periodic_action(
                download_book(book_id, preferred_format),
                update,
                context,
                action=ChatAction.UPLOAD_DOCUMENT,
                interval=4,
            )
            # карточку отправляем всегда
            await send_book_details_message(update, context, details)

            chat_id = update.effective_chat.id if update.effective_chat else user_id
            await context.bot.send_document(
                chat_id=chat_id,
                document=file_data,
                filename=f"{details.get('title','book')[:50]}_{book_id}.{preferred_format}",
                caption=f"{details.get('title','')}\nАвтор: {details.get('author','')}",
            )
        except Exception:
            logger.exception("Ошибка при скачивании книги")
            await send_book_details_message(update, context, details)
    else:
        await send_book_details_message(update, context, details)


def _build_response_lines(books: list, authors: list) -> list[str]:
    """Готовит строки результата (для пагинации)."""
    lines: list[str] = []
    if authors:
        lines.append(f"📖 <b>Найдено авторов:</b> {len(authors)}\n")
        for a in authors:
            lines.append(
                f"• <b>{a['name']}</b> — {a['book_count']} книг\n"
                f"  <u>/author{a['id']}</u>\n\n"
            )
    if books:
        lines.append(f"📚 <b>Найдено книг:</b> {len(books)}\n")
        for b in books:
            lines.append(
                f"• <b>{b['title']}</b>\n"
                f"  Автор: <i>{b['author']}</i>\n"
                f"  Скачать: <u>/download{b['id']}</u>\n\n"
            )
    return lines


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает входящие текстовые сообщения:
    - /download<ID>[@...]
    - /author<ID>[@...]
    - текстовый поиск
    """
    await set_typing_action(update, context)

    if update.message is None or update.message.text is None:
        await _safe_reply_text(update, context, "Я понимаю только текстовые сообщения.")
        return

    text = update.message.text.strip()
    # ✂️ убираем @... если есть
    if "@" in text:
        text = text.split("@", 1)[0]

    user = update.effective_user
    chat = update.effective_chat
    user_id = user.id if user else 0
    chat_id = chat.id if chat else 0
    logger.info("%s:%s -> %s", user_id, chat_id, text)

    # --- /download<ID> ---
    m = re.match(r"^/download(\d+)$", text, re.IGNORECASE)
    if m:
        book_id = m.group(1)
        await handle_download_command(book_id, update, context)
        return

    # --- /author<ID> ---
    if text.lower().startswith("/author"):
        await author_books_command(update, context)
        return

    # --- Поиск ---
    try:
        mode = get_user_ephemeral_mode(user_id)
        if mode is None:
            settings = await get_user_settings(user_id)
            mode = settings.get("preferred_search_mode") or "general"

        data = await run_with_periodic_action(
            search_books_and_authors(text, mode),
            update,
            context,
            action=ChatAction.TYPING,
            interval=4,
        )
        clear_user_ephemeral_mode(user_id)
    except Exception:
        logger.exception("Ошибка при поиске книг и авторов")
        await _safe_reply_text(update, context, "Ошибка при поиске.")
        return

    books = data.get("books_found", [])
    authors = data.get("authors_found", [])

    if authors:
        for a in authors:
            set_author_mapping(a["id"], a["name"])

    if not books and not authors:
        await _safe_reply_text(update, context, "Ничего не найдено.")
        return

    lines = _build_response_lines(books, authors)
    total_pages = max(1, (len(lines) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE)
    set_user_search_data(user_id, lines, total_pages)

    page_text = build_page_text(user_id)
    kb = build_pagination_kb(user_id)

    await send_or_edit_message(update, page_text, reply_markup=kb)
