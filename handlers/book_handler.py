#book_details.py

import logging
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
)
from telegram.constants import ChatAction
from services.service import (
    get_book_details,
    download_book,
)
from services.db import get_user_settings
from utils.utils import sanitize_filename
from utils.chat_actions import set_upload_document_action, run_with_periodic_action

logger = logging.getLogger(__name__)


# Функция для отправки красивого сообщения с кнопками форматов
async def send_book_details_message(update: Update, context: ContextTypes.DEFAULT_TYPE, details: dict):
    parts = []
    parts.append(details["title"] or "Без названия")
    if details["author"]:
        parts.append(f"Автор: {details['author']}")
    if details.get("year"):
        parts.append(f"Год: {details['year']}")
    if details.get("annotation"):
        parts.append(f"\n{details['annotation']}")
    cap = "\n".join(parts)

    fmts = details.get("formats", [])
    if fmts:
        row = [InlineKeyboardButton(f, callback_data=f"choose_format|{details['id']}|{f}") for f in fmts]
        kb = InlineKeyboardMarkup([row])
    else:
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Отсутствуют поддерживаемые форматы", callback_data="no-op")]])

    cover = None
    if details.get("cover_url"):
        try:
            r = requests.get(details["cover_url"], timeout=10)
            if r.status_code == 200:
                cover = r.content
        except Exception as e:
            logging.exception("Ошибка при получении обложки:", exc_info=e)
    if cover:
        msg = await update.message.reply_photo(
            photo=cover,
            caption=cap,
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        msg = await update.message.reply_text(
            text=cap,
            parse_mode="HTML",
            reply_markup=kb
        )
    return msg.message_id

# Обработка inline-кнопок для выбора формата
async def choose_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_upload_document_action(update, context)
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.exception("Ошибка при вызове query.answer():")

    data = query.data
    _, book_id, fmt = data.split("|")
    
    try:
        logger.info(f"Начало операции скачивания книги (inline) для book_id {book_id}")
        file_data = await run_with_periodic_action(
            download_book(book_id, fmt),
            update,
            context,
            action=ChatAction.UPLOAD_DOCUMENT,
            interval=4
        )
        logger.info(f"Операция скачивания книги (inline) завершена для book_id {book_id}")
    except Exception as e:
        logger.exception("Ошибка при скачивании книги через inline-кнопку:")
        await query.message.reply_text("Ошибка скачивания книги.")
        return

    try:
        logger.info(f"Начало операции получения деталей книги (inline) для book_id {book_id}")
        d = await run_with_periodic_action(
            get_book_details(book_id),
            update,
            context,
            action=ChatAction.UPLOAD_DOCUMENT,
            interval=4
        )
        logger.info(f"Операция получения деталей книги (inline) завершена для book_id {book_id}")
    except Exception as e:
        logger.exception("Ошибка при получении деталей книги через inline-кнопку:")
        d = {"title": f"book_{book_id}", "author": ""}

    title = d.get("title") or "Без названия"
    author = d.get("author") or "Неизвестен"
    caption = f"{title[:50]}\nАвтор: {author}"
    
    st = await get_user_settings(query.from_user.id)
    naming = st.get("preferred_book_naming") or "title_author"
    if naming == "title":
        fname = title
    elif naming == "title_id":
        fname = f"{title}_{book_id}"
    elif naming == "title_author":
        fname = f"{title}_{author}"
    elif naming == "title_author_id":
        fname = f"{title}_{author}_{book_id}"
    else:
        fname = f"{title}_{author}"
    
    filename = f"{sanitize_filename(fname)}.{fmt}"
    
    await context.bot.send_document(
        chat_id=query.message.chat_id,
        document=file_data,
        filename=filename,
        caption=caption
    )