# handlers/author_books.py

import logging
import re
from typing import Optional

from telegram import Update
from telegram.ext import ContextTypes

from services.service import get_author_books
from config import SEARCH_RESULTS_PER_PAGE
from utils.chat_actions import set_typing_action
from utils.pagination import build_page_text, build_pagination_kb
from utils.state import get_author_mapping, set_user_search_data

logger = logging.getLogger(__name__)


async def _safe_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """
    Пытается отправить текст пользователю вне зависимости от наличия message.
    Не бросает исключений наружу.
    """
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


async def author_books_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду /author<ID> (с возможным @BotName).
    Примеры:
      /author123456
      /author123456@MyBot
    """
    await set_typing_action(update, context)

    user = update.effective_user
    if user is None:
        logger.warning("author_books_command: effective_user is None")
        await _safe_reply_text(update, context, "Не удалось определить пользователя.")
        return
    user_id = user.id

    if update.message is None or not update.message.text:
        logger.warning("author_books_command: message или текст отсутствуют")
        await _safe_reply_text(update, context, "Некорректная команда. Используйте формат: /author<ID>")
        return

    # исходный текст команды
    text = update.message.text.strip()
    # ✂️ если есть "@..." — отрезаем
    if "@" in text:
        text = text.split("@", 1)[0]

    # парсим ID автора
    m = re.match(r"^/author(\d+)$", text, re.IGNORECASE)
    if not m:
        await _safe_reply_text(update, context, "Некорректная команда. Используйте формат: /author<ID>")
        return

    author_id = m.group(1)
    default_author = get_author_mapping(author_id)

    try:
        books = await get_author_books(author_id, default_author=default_author)
    except Exception as e:
        logger.exception("Ошибка при получении книг автора %s: %s", author_id, e)
        await _safe_reply_text(update, context, "Не удалось получить книги автора.")
        return

    if not books:
        await _safe_reply_text(update, context, "У автора нет книг или он не найден.")
        return

    # Формируем карточки для пагинации
    def _line(title: Optional[str], author: Optional[str], bid: Optional[str]) -> str:
        t = title or "Без названия"
        a = author or "Неизвестен"
        b = bid or "N/A"
        return f"{t}\n{a}\nСкачать: /download{b}\n"

    records = [_line(b.get("title"), b.get("author"), b.get("id")) for b in books]

    total_pages = max(1, (len(records) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE)
    set_user_search_data(user_id, records, total_pages)

    page_text = build_page_text(user_id)
    keyboard = build_pagination_kb(user_id)

    try:
        if update.message is not None:
            await update.message.reply_text(page_text, reply_markup=keyboard)
        else:
            await _safe_reply_text(update, context, page_text)
    except Exception as e:
        logger.exception("Не удалось отправить список книг автора пользователю %s: %s", user_id, e)
        await _safe_reply_text(update, context, "Ошибка при отправке списка книг автора.")
