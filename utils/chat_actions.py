#chat_actions.py

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from contextlib import suppress

logger = logging.getLogger(__name__)

async def set_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет статус "печатает..." в чат.

    Args:
        update (Update): Обновление Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
    """
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.TYPING
    )

async def set_upload_document_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет статус "загружает документ..." в чат.

    Args:
        update (Update): Обновление Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
    """
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_DOCUMENT
    )

async def periodic_chat_action(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str, interval: float, stop_event: asyncio.Event):
    """
    Периодически отправляет заданный chat action до установки флага остановки.

    Args:
        update (Update): Обновление Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
        action (str): Действие, которое отправляется (например, ChatAction.TYPING).
        interval (float): Интервал между отправками действия (в секундах).
        stop_event (asyncio.Event): Событие, которое прекращает отправку, когда установлено.
    """
    while not stop_event.is_set():
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=action
        )
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)

async def run_with_periodic_action(coro, update: Update, context: ContextTypes.DEFAULT_TYPE, action: str = ChatAction.TYPING, interval: float = 4):
    """
    Запускает корутину параллельно с периодическим обновлением chat action.
    Как только основная корутина завершается, периодическая отправка прекращается.

    Args:
        coro (Awaitable[Any]): Корутина, которую необходимо выполнить.
        update (Update): Обновление Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
        action (str, optional): Действие, которое будет отправляться периодически. По умолчанию ChatAction.TYPING.
        interval (float, optional): Интервал между отправками действия (в секундах). По умолчанию 4.0.

    Returns:
        Any: Результат выполнения корутины.
    """
    stop_event = asyncio.Event()
    periodic_task = asyncio.create_task(periodic_chat_action(update, context, action, interval, stop_event))
    try:
        result = await coro
        return result
    finally:
        stop_event.set()
        await periodic_task