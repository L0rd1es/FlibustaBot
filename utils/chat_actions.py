#chat_actions.py

import asyncio
from telegram import (
    Update,
)
from telegram.ext import (
    ContextTypes,
)
from telegram.constants import ChatAction

# Функция отправки chat_action "печатает..."
async def set_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

# Функция отправки chat_action "загружает документ..."
async def set_upload_document_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_DOCUMENT
    )

# Периодически отправляет заданный chat action, пока не установлен stop_event.
async def periodic_chat_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, interval: float, stop_event: asyncio.Event):
    while not stop_event.is_set():
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=action
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue

# Запускает корутину coro параллельно с периодическим обновлением chat action.
# Как только coro завершается, периодическое обновление останавливается.
async def run_with_periodic_action(coro, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str = ChatAction.TYPING, interval: float = 4):
    stop_event = asyncio.Event()
    periodic_task = asyncio.create_task(periodic_chat_action(update, context, action, interval, stop_event))
    try:
        result = await coro
        return result
    finally:
        stop_event.set()
        await periodic_task