#utils.py

import re
from telegram import Update
from telegram.ext import ContextTypes

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
