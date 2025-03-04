#utils.py

import re
from telegram import Update
from telegram.ext import ContextTypes

async def no_op_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("")

# Удаляет недопустимые символы для имени файла и обрезает лишние пробелы.
def sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()
