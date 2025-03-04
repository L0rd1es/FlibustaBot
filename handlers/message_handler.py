import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from services.service import search_books_and_authors, get_book_details, download_book
from services.db import get_user_settings
from config import SEARCH_RESULTS_PER_PAGE
from utils.chat_actions import set_typing_action, run_with_periodic_action
from utils.pagination import build_page_text, build_pagination_kb
from handlers.author_handler import author_books_command
from handlers.book_handler import send_book_details_message
from utils.state import set_author_mapping, set_user_search_data, get_user_ephemeral_mode, clear_user_ephemeral_mode

logger = logging.getLogger(__name__)

async def handle_download_command(book_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает команду загрузки книги.

    Функция принимает идентификатор книги, проверяет его корректность, затем получает детали книги и, если у пользователя
    установлен предпочтительный формат, пытается скачать книгу в этом формате. В случае успешного скачивания отправляет
    книгу вместе с её деталями, иначе – отправляет только детали книги.

    Параметры:
        book_id (str): Идентификатор книги, переданный командой.
        update (Update): Обновление, полученное от Telegram.
        context (ContextTypes.DEFAULT_TYPE): Контекст выполнения.
    """
    if not book_id.isdigit():
        await update.message.reply_text("Некорректный ID.")
        return

    try:
        logger.info(f"Получение деталей книги для book_id {book_id}")
        details = await run_with_periodic_action(
            get_book_details(book_id), update, context,
            action=ChatAction.TYPING, interval=4
        )
    except Exception as e:
        logger.exception("Ошибка при получении деталей книги:")
        await update.message.reply_text("Не удалось получить книгу.")
        return

    user_id = update.effective_user.id
    settings = await get_user_settings(user_id)
    preferred_format = settings.get("preferred_format")

    if preferred_format and (preferred_format in details["formats"]):
        try:
            logger.info(f"Скачивание книги book_id {book_id} в формате {preferred_format}")
            file_data = await run_with_periodic_action(
                download_book(book_id, preferred_format),
                update,
                context,
                action=ChatAction.UPLOAD_DOCUMENT,
                interval=4
            )
            await send_book_details_message(update, context, details)
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file_data,
                filename=f"{details['title'][:50]}_{book_id}.{preferred_format}",
                caption=f"{details['title']}\nАвтор: {details['author']}"
            )
        except Exception as e:
            logger.exception("Ошибка при скачивании книги:")
            await send_book_details_message(update, context, details)
    else:
        await send_book_details_message(update, context, details)

def build_response_text(books: list, authors: list) -> str:
    response_lines = []
    if authors:
        response_lines.append(f"Найдено авторов: {len(authors)}\n")
        for author in authors:
            response_lines.append(
                f"{author['name']} - {author['book_count']} книг\nКниги автора: /author{author['id']}\n\n"
            )
    if books:
        response_lines.append(f"Найдено книг: {len(books)}\n")
        for book in books:
            response_lines.append(
                f"{book['title']}\n{book['author']}\nСкачать: /download{book['id']}\n\n"
            )
    return "".join(response_lines)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает входящие текстовые сообщения от пользователя.
    
    В зависимости от содержания сообщения выполняет:
      - Загрузку книги (/download)
      - Поиск авторов и книг
      - Перенаправление к другим обработчикам команд
    """
    await set_typing_action(update, context)
    text = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    logger.info(f"{user_id}:{chat_id} -> {text}")

    if text.startswith("/download"):
        book_id = text.removeprefix("/download").strip()
        await handle_download_command(book_id, update, context)
        return

    if text.startswith("/author") and text[7:].isdigit():
        await author_books_command(update, context)
        return

    try:
        mode = get_user_ephemeral_mode(user_id)
        if mode is None:
            settings = await get_user_settings(user_id)
            mode = settings.get("preferred_search_mode") or "general"

        data = await search_books_and_authors(text, mode)
        clear_user_ephemeral_mode(user_id)
    except Exception as e:
        logger.exception("Ошибка при поиске книг и авторов:")
        await update.message.reply_text("Ошибка при поиске.")
        return

    books = data.get("books_found", [])
    authors = data.get("authors_found", [])

    if authors:
        for author in authors:
            set_author_mapping(author["id"], author["name"])

    if not books and not authors:
        await update.message.reply_text("Ничего не найдено.")
        return

    records = []
    if authors:
        records.append(f"Найдено авторов: {len(authors)}\n")
        for author in authors:
            records.append(
                f"{author['name']} - {author['book_count']} книг\nКниги автора: /author{author['id']}\n"
            )
    if books:
        records.append(f"Найдено книг: {len(books)}\n")
        for book in books:
            records.append(
                f"{book['title']}\n{book['author']}\nСкачать: /download{book['id']}\n"
            )

    total_pages = (len(records) + SEARCH_RESULTS_PER_PAGE - 1) // SEARCH_RESULTS_PER_PAGE
    set_user_search_data(user_id, records, total_pages)

    page_text = build_page_text(user_id)
    pagination_keyboard = build_pagination_kb(user_id)
    await update.message.reply_text(page_text, reply_markup=pagination_keyboard)
