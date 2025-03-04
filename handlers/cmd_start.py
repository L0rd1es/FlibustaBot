#start.py

from telegram import (
    Update,
)
from telegram.ext import (
    ContextTypes,
)
from utils.chat_actions import set_typing_action

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    text = (
        "Привет! Я бот для поиска книг на Флибусте.\n\n"
        "Команды:\n"
        "/search - Общий поиск (1 раз)\n"
        "/book - Поиск книг (1 раз)\n"
        "/author - Поиск авторов (1 раз)\n"
        "/settings - Настройки формата/режима\n\n"
        "Просто введи запрос...\n"
        "Скачать: /download123\n"
        "Автор: /author123\n"
    )
    await update.message.reply_text(text)