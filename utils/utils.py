# utils/utils.py

import re
import logging
from typing import Optional, Union

from telegram import (
    Update,
    InlineKeyboardMarkup,
    CallbackQuery,
    Message,               # <-- важно для isinstance
    InaccessibleMessage,   # <-- на всякий случай, если захочешь использовать
)
from telegram.ext import ContextTypes
from telegram.error import BadRequest

logger = logging.getLogger(__name__)


async def no_op_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает callback без выполнения каких-либо действий (no-op) и убирает «крутилку».
    """
    try:
        if update.callback_query:
            await update.callback_query.answer(cache_time=0, show_alert=False)
    except Exception as e:
        logger.debug("no_op_callback answer failed: %s", e)


def sanitize_filename(name: str) -> str:
    """
    Удаляет недопустимые символы из имени файла и обрезает лишние пробелы.
    """
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip()


def shorten_title(title: str, max_length: int) -> str:
    """
    Очищает название от всех символов, кроме букв, цифр и _, заменяет пробелы на _
    и обрезает корректно по словам; если ни одно слово не помещается — режет жёстко.
    """
    title = re.sub(r"[^\w\s]", "", title)
    title = title.replace(" ", "_")

    if len(title) <= max_length:
        return title

    words = title.split("_")
    shortened_title = ""
    for word in words:
        extra = 1 if shortened_title else 0
        if len(shortened_title) + extra + len(word) > max_length:
            break
        shortened_title += ("_" if shortened_title else "") + word
    return shortened_title if shortened_title else title[:max_length]


async def _edit_text_or_caption(
    cq: CallbackQuery,
    *,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup],
) -> bool:
    """
    Пытается отредактировать текст (или подпись) вместе с клавиатурой.
    Возвращает True, если изменения применены.
    Если сообщение недоступно (InaccessibleMessage), возвращает False.
    """
    msg = cq.message
    if msg is None or not isinstance(msg, Message):
        # Нельзя безопасно обращаться к .text/.caption — пусть вызывающий попробует сменить только клавиатуру
        return False

    try:
        if msg.text is not None:
            # Обычное текстовое сообщение
            await cq.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        else:
            # Сообщение с медиа и подписью
            await cq.edit_message_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        return True
    except BadRequest as e:
        # Телеграм сообщает, что контент не изменился — это не критично
        if "Message is not modified" in str(e):
            logger.debug("edit_message_text/caption: Message is not modified")
            return False
        raise
    except Exception:
        logger.exception("Unexpected error in _edit_text_or_caption")
        return False


async def _edit_only_markup(
    cq: CallbackQuery,
    *,
    reply_markup: Optional[InlineKeyboardMarkup],
) -> bool:
    """
    Пытается отредактировать только клавиатуру.
    Возвращает True, если изменения применены.
    """
    try:
        await cq.edit_message_reply_markup(reply_markup=reply_markup)
        return True
    except BadRequest as e:
        if "Message is not modified" in str(e):
            logger.debug("edit_message_reply_markup: Message is not modified")
            return False
        raise
    except Exception:
        logger.exception("Unexpected error in _edit_only_markup")
        return False


async def send_or_edit_message(
    update_or_query: Union[Update, CallbackQuery],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """
    Универсальная отправка/редактирование.
    Алгоритм для callback:
      1) answer()
      2) попытаться править текст/подпись с клавиатурой
      3) если "not modified" — попробовать править только клавиатуру
      4) если и это "not modified" — игнор без ошибки
    Для обычного Update — reply_text().
    """
    # Ветка: передали сам CallbackQuery
    if isinstance(update_or_query, CallbackQuery):
        try:
            await update_or_query.answer(cache_time=0, show_alert=False)
        except Exception as e:
            logger.debug("send_or_edit_message: answer failed (raw CQ): %s", e)

        try:
            changed = await _edit_text_or_caption(update_or_query, text=text, reply_markup=reply_markup)
            if not changed:
                await _edit_only_markup(update_or_query, reply_markup=reply_markup)
        except BadRequest as e:
            logger.error("Ошибка редактирования (CallbackQuery): %s", e)
        except Exception:
            logger.exception("Неожиданная ошибка редактирования (CallbackQuery)")
        return

    # Ветка: Update, у которого есть callback_query
    if getattr(update_or_query, "callback_query", None):
        cq: CallbackQuery = update_or_query.callback_query  # type: ignore[attr-defined]
        try:
            await cq.answer(cache_time=0, show_alert=False)
        except Exception as e:
            logger.debug("send_or_edit_message: answer failed (Update.cq): %s", e)

        try:
            changed = await _edit_text_or_caption(cq, text=text, reply_markup=reply_markup)
            if not changed:
                await _edit_only_markup(cq, reply_markup=reply_markup)
        except BadRequest as e:
            logger.error("Ошибка редактирования (Update.cq): %s", e)
        except Exception:
            logger.exception("Неожиданная ошибка редактирования (Update.cq)")
        return

    # Ветка: обычное сообщение (reply)
    if getattr(update_or_query, "message", None):
        try:
            await update_or_query.message.reply_text(  # type: ignore[attr-defined]
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error("Ошибка отправки сообщения: %s", e)
        return

    logger.warning("send_or_edit_message: неизвестный тип update_or_query: %r", type(update_or_query))
