import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from services.service import (
    search_books_and_authors,
    get_book_details,
    download_book,
)
from services.db import get_user_settings
from config import SEARCH_RESULTS_PER_PAGE, STATS_FILE
from utils.chat_actions import set_typing_action, run_with_periodic_action
from utils.pagination import build_page_text, build_pagination_kb
from handlers.author_handler import author_books_command
from handlers.book_handler import send_book_details_message
from utils.state import (
    set_author_mapping, set_user_search_data,
    get_user_ephemeral_mode, clear_user_ephemeral_mode,
)

logger = logging.getLogger(__name__)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    text = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    with open(STATS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user_id}:{chat_id} -> {text}\n")

    if text.startswith("/download"):
        book_id = text.removeprefix("/download").strip()
        if not book_id.isdigit():
            await update.message.reply_text("Некорректный ID.")
            return
        try:
            logger.info(f"Получение деталей книги для book_id {book_id}")
            det = await run_with_periodic_action(
                get_book_details(book_id), update, context,
                action=ChatAction.TYPING, interval=4
            )
        except Exception as e:
            logger.exception("Ошибка при получении деталей книги:")
            await update.message.reply_text("Не удалось получить книгу.")
            return

        st = await get_user_settings(user_id)
        pfmt = st.get("preferred_format")

        if pfmt and (pfmt in det["formats"]):
            try:
                logger.info(f"Скачивание книги book_id {book_id} в формате {pfmt}")
                file_data = await run_with_periodic_action(
                    download_book(book_id, pfmt),
                    update,
                    context,
                    action=ChatAction.UPLOAD_DOCUMENT,
                    interval=4
                )
                await send_book_details_message(update, context, det)
                await context.bot.send_document(
                    chat_id=chat_id,
                    document=file_data,
                    filename=f"{det['title'][:50]}_{book_id}.{pfmt}",
                    caption=f"{det['title']}\nАвтор: {det['author']}"
                )
            except Exception as e:
                logger.exception("Ошибка при скачивании книги:")
                await send_book_details_message(update, context, det)
        else:
            await send_book_details_message(update, context, det)
        return

    if text.startswith("/author") and text[7:].isdigit():
        await author_books_command(update, context)
        return

    try:
        mode = get_user_ephemeral_mode(user_id)
        if mode is None:
            st = await get_user_settings(user_id)
            mode = st["preferred_search_mode"] if st["preferred_search_mode"] else "general"

        data = await search_books_and_authors(text, mode)
        clear_user_ephemeral_mode(user_id)

    except Exception as e:
        logger.exception("Ошибка при поиске книг и авторов:")
        await update.message.reply_text("Ошибка при поиске.")
        return

    bks = data["books_found"]
    auts = data["authors_found"]

    if auts:
        for a in auts:
            set_author_mapping(a["id"], a["name"])

    if not bks and not auts:
        await update.message.reply_text("Ничего не найдено.")
        return

    recs = []

    if auts:
        recs.append(f"Найдено авторов: {len(auts)}\n")
        for a in auts:
            recs.append(f"{a['name']} - {a['book_count']} книг\nКниги автора: /author{a['id']}\n")

    if bks:
        recs.append(f"Найдено книг: {len(bks)}\n")
        for b in bks:
            recs.append(f"{b['title']}\n{b['author']}\nСкачать: /download{b['id']}\n")

    total_pages = (len(recs) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
    set_user_search_data(user_id, recs, total_pages)

    txt = build_page_text(user_id)
    kb = build_pagination_kb(user_id)
    await update.message.reply_text(txt, reply_markup=kb)
