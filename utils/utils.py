#utils.py

import re
from telegram import Update
from telegram.ext import ContextTypes
import logging
from typing import Optional, Union
from telegram import Update, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def no_op_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает callback без выполнения каких-либо действий.

    Используется для кнопок, которые не должны ничего делать (no operation).
    """
    await update.callback_query.answer("")

def sanitize_filename(name: str) -> str:
    """
    Удаляет недопустимые символы из имени файла и обрезает лишние пробелы.

    Args:
        name (str): Исходное имя файла.

    Returns:
        str: Очищенное имя файла.
    """
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()

def shorten_title(title: str, max_length: int) -> str:
    """Очищает название от всех символов, кроме букв, цифр и _, заменяет пробелы на _ и обрезает корректно."""
    title = re.sub(r"[^\w\s]", "", title)
    title = title.replace(" ", "_")

    if len(title) <= max_length:
        return title

    words = title.split("_")
    shortened_title = ""

    for word in words:
        if len(shortened_title) + len(word) + 1 > max_length:
            break
        shortened_title += f"_{word}" if shortened_title else word

    return shortened_title

async def send_or_edit_message(
    update_or_query: Union[Update, CallbackQuery],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """
    Отправляет или редактирует сообщение с поддержкой HTML-разметки.
    """
    if hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
        query: CallbackQuery = update_or_query.callback_query
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
    elif isinstance(update_or_query, CallbackQuery):
        try:
            await update_or_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
    else:
        try:
            await update_or_query.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {e}")
