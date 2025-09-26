# chat_actions.py

import asyncio
import logging
from contextlib import suppress
from typing import Awaitable, TypeVar

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _get_chat_id(update: Update) -> int:
    """Безопасно достаём chat_id или бросаем ValueError (чтобы не падать молча)."""
    chat = update.effective_chat
    if chat is None:
        raise ValueError("effective_chat is None — невозможно отправить chat action.")
    return chat.id


async def set_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет статус "печатает..." в чат.

    Args:
        update (Update): Обновление Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
    """
    try:
        chat_id = _get_chat_id(update)
    except ValueError as e:
        logger.warning("set_typing_action: %s", e)
        return

    try:
        await context.bot.send_chat_action(
            chat_id=chat_id,
            action=ChatAction.TYPING
        )
    except Exception as e:
        # Не роняем хендлер из-за временных сетевых/лимитных ошибок
        logger.warning("set_typing_action failed: %s", e)


async def set_upload_document_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет статус "загружает документ..." в чат.

    Args:
        update (Update): Обновление Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
    """
    try:
        chat_id = _get_chat_id(update)
    except ValueError as e:
        logger.warning("set_upload_document_action: %s", e)
        return

    try:
        await context.bot.send_chat_action(
            chat_id=chat_id,
            action=ChatAction.UPLOAD_DOCUMENT
        )
    except Exception as e:
        logger.warning("set_upload_document_action failed: %s", e)


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
    try:
        chat_id = _get_chat_id(update)
    except ValueError as e:
        logger.warning("periodic_chat_action: %s", e)
        return

    # Если пришёл некорректный интервал, мягко используем дефолт из оригинала
    if interval is None or interval <= 0:
        interval = 4.0

    while not stop_event.is_set():
        try:
            await context.bot.send_chat_action(
                chat_id=chat_id,
                action=action
            )
        except Exception as e:
            # Логируем и продолжаем — не срываем периодическую отправку
            logger.warning("periodic_chat_action send failed: %s", e)

        # ждем либо остановку, либо таймаут
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

    # Создаём фоновую задачу связанную с жизненным циклом приложения, если доступно
    create_task = getattr(context.application, "create_task", asyncio.create_task)
    periodic_task = create_task(
        periodic_chat_action(update, context, action, interval, stop_event)
    )

    try:
        result = await coro
        return result
    finally:
        # Сигнализируем о завершении и корректно дожидаемся фоновой задачи
        stop_event.set()
        if not periodic_task.done():
            # мягкая отмена, если задача еще в ожидании таймера
            periodic_task.cancel()
            with suppress(asyncio.CancelledError):
                await periodic_task
