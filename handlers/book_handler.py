# handlers/book_handler.py

import logging
from typing import Iterable, List, Sequence

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.ext import ContextTypes

from services.service import get_book_details, download_book
from services.db import get_user_settings
from utils.utils import sanitize_filename, shorten_title
from utils.chat_actions import set_upload_document_action, run_with_periodic_action
from config import MAX_TITLE_LENGTH

logger = logging.getLogger(__name__)

CAPTION_LIMIT = 1024  # лимит подписи к медиа в Telegram


def _chunk(seq: Sequence[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


def _trim_caption_for_photo(text: str, limit: int = CAPTION_LIMIT) -> str:
    """Безопасно подрезает caption под лимит Telegram (1024)."""
    if len(text) <= limit:
        return text
    hard_limit = max(0, limit - 3)
    return text[:hard_limit] + "…"


async def _safe_reply_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int:
    """Пишет текст либо через message.reply_text, либо в чат напрямую — возвращает message_id."""
    if update.message:
        msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return msg.message_id
    if update.effective_chat:
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id, text=text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
        return msg.message_id
    logger.warning("Нет ни message, ни effective_chat — некуда отправлять текст.")
    return 0


async def _safe_reply_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    photo: str,
    caption: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> int:
    """Отправляет фото с подписью. Если не получилось — отправляет текст. Возвращает message_id."""
    cap = _trim_caption_for_photo(caption)
    try:
        if update.message:
            msg = await update.message.reply_photo(
                photo=photo, caption=cap, parse_mode=ParseMode.HTML, reply_markup=reply_markup
            )
            return msg.message_id
        if update.effective_chat:
            msg = await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=cap,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            return msg.message_id
    except Exception as e:
        logger.warning("Не удалось отправить фото по URL (%s). Падаем на текст: %s", photo, e)

    # fallback — просто текст
    return await _safe_reply_text(update, context, caption, reply_markup)


async def send_book_details_message(update: Update, context: ContextTypes.DEFAULT_TYPE, details: dict) -> int:
    """
    Отправляет сообщение с подробностями о книге и кнопками для выбора формата.
    Возвращает message_id отправленного сообщения.
    """
    title = details.get("title") or "Без названия"

    parts: list[str] = [f"📚 <i><b>{title}</b></i>"]

    if details.get("author"):
        parts.append("━━━━━━━━━━━━━")
        parts.append(f"👤 <b>Автор:</b> {details['author']}")
    if details.get("year"):
        parts.append(f"📅 <b>Год:</b> {details['year']}")
    if details.get("annotation"):
        parts.append("━━━━━━━━━━━━━")
        parts.append(f"📝 <i>{details['annotation']}</i>")

    caption = "\n".join(parts)

    # Кнопки форматов — аккуратно и детерминированно
    formats_raw = details.get("formats") or []
    formats = sorted(
        set(formats_raw),
        key=lambda x: ("fb2", "epub", "mobi", "pdf").index(x) if x in ("fb2", "epub", "mobi", "pdf") else 999,
    )

    if not formats:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Отсутствуют поддерживаемые форматы", callback_data="no-op")]]
        )
    else:
        rows: list[list[InlineKeyboardButton]] = []
        for row_formats in _chunk(formats, 3):
            row = [
                InlineKeyboardButton(fmt, callback_data=f"choose_format|{details['id']}|{fmt}")
                for fmt in row_formats
            ]
            rows.append(row)
        keyboard = InlineKeyboardMarkup(rows)

    if details.get("cover_url"):
        return await _safe_reply_photo(update, context, details["cover_url"], caption, keyboard)
    else:
        return await _safe_reply_text(update, context, caption, keyboard)


async def choose_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает выбор формата книги пользователем и отправляет файл книги.
    """
    await set_upload_document_action(update, context)

    query = update.callback_query
    if not query:
        logger.error("choose_format_callback: callback_query отсутствует")
        return

    try:
        await query.answer()
    except Exception as e:
        logger.exception("Ошибка при query.answer(): %s", e)

    data = (query.data or "").strip()
    parts = data.split("|")

    if len(parts) != 3 or parts[0] != "choose_format":
        logger.error("Некорректные данные в callback: %s", data)
        # Используем безопасную отправку текста — без прямого обращения к query.message.reply_text
        await _safe_reply_text(update, context, "Получены некорректные данные. Пожалуйста, попробуйте снова.")
        return

    _, book_id, fmt = parts

    # 1) Скачиваем файл (с периодическим Chat Action)
    try:
        logger.info("Скачивание книги %s в формате %s", book_id, fmt)
        file_data = await run_with_periodic_action(
            download_book(book_id, fmt),
            update,
            context,
            action=ChatAction.UPLOAD_DOCUMENT,
            interval=4,
        )
        if not file_data:
            raise ValueError("Пустой файл книги.")
        logger.info("Книга %s в формате %s скачана", book_id, fmt)
    except Exception as e:
        logger.exception("Ошибка скачивания книги %s (%s): %s", book_id, fmt, e)
        await _safe_reply_text(update, context, "Ошибка скачивания книги.")
        return

    # 2) Получаем детали (для имени файла)
    try:
        logger.info("Получение деталей книги %s", book_id)
        details = await run_with_periodic_action(
            get_book_details(book_id),
            update,
            context,
            action=ChatAction.UPLOAD_DOCUMENT,
            interval=4,
        )
        logger.info("Детали книги %s получены", book_id)
    except Exception as e:
        logger.exception("Ошибка получения деталей книги %s: %s", book_id, e)
        details = {"title": f"book_{book_id}", "author": ""}

    title = details.get("title") or "Без названия"
    author = details.get("author") or "Неизвестен"

    # 3) Читаем настройки пользователя (с учётом None)
    try:
        settings = await get_user_settings(query.from_user.id)
        naming = (settings.get("preferred_book_naming") if settings else None) or "title_author"
    except Exception as e:
        logger.warning("Не удалось получить настройки пользователя: %s", e)
        naming = "title_author"

    # 4) Формируем адекватное имя файла
    shortened_title = shorten_title(title, MAX_TITLE_LENGTH)
    shortened_author = shorten_title(author, MAX_TITLE_LENGTH // 2)

    name_options = {
        "title": f"{shortened_title}",
        "title_id": f"{shortened_title}_{book_id}",
        "title_author": f"{shortened_title}_{shortened_author}",
        "title_author_id": f"{shortened_title}_{shortened_author}_{book_id}",
    }
    raw_name = name_options.get(naming, f"{shortened_title}_{shortened_author}")

    try:
        filename = f"{sanitize_filename(raw_name)}.{fmt}"
    except Exception as e:
        logger.warning("Ошибка при обработке имени файла '%s': %s", raw_name, e)
        filename = f"book_{book_id}.{fmt}"

    # 5) Отправляем документ
    # 5) Отправляем документ
    chat_id: int | None = None
    if query is not None and query.message is not None and getattr(query.message, "chat", None) is not None:
        chat_id = query.message.chat.id
    elif update.effective_chat is not None:
        chat_id = update.effective_chat.id

    if chat_id is None:
        logger.error("Нет chat_id для отправки файла %s", filename)
        return

    try:
        await context.bot.send_document(chat_id=chat_id, document=file_data, filename=filename)
    except Exception as e:
        logger.exception("Ошибка при отправке файла %s пользователю %s: %s", filename, chat_id, e)
        await _safe_reply_text(update, context, "Ошибка при отправке файла.")
