#help.py

from telegram import (
    Update,
)
from telegram.ext import (
    ContextTypes,
)
from utils.chat_actions import set_typing_action

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    text = (
        "Помощь:\n"
        "/start - Начало\n"
        "/help - Это сообщение\n"
        "/settings - Настройки\n"
        "/search /book /author - одноразовые режимы\n\n"
        "Скачивание: /download<id>\n"
        "Автор: /author<id>\n"
    )
    await update.message.reply_text(text)