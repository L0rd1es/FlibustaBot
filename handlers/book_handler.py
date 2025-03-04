import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatAction
from services.service import get_book_details, download_book
from services.db import get_user_settings
from utils.utils import sanitize_filename, shorten_title
from utils.chat_actions import set_upload_document_action, run_with_periodic_action
from config import MAX_TITLE_LENGTH

logger = logging.getLogger(__name__)

async def send_book_details_message(update: Update, context: ContextTypes.DEFAULT_TYPE, details: dict) -> int:
    """
    Отправляет сообщение с подробностями о книге и кнопками для выбора формата.

    :param update: Объект обновления Telegram.
    :param context: Контекст выполнения.
    :param details: Словарь с деталями книги.
    :return: Идентификатор отправленного сообщения.
    """
    parts = [details.get("title", "Без названия")]
    if details.get("author"):
        parts.append(f"Автор: {details['author']}")
    if details.get("year"):
        parts.append(f"Год: {details['year']}")
    if details.get("annotation"):
        parts.append(f"\n{details['annotation']}")
    caption = "\n".join(parts)

    formats = details.get("formats", [])
    if not formats:
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Отсутствуют поддерживаемые форматы", callback_data="no-op")]])
    else:
        row = [InlineKeyboardButton(fmt, callback_data=f"choose_format|{details['id']}|{fmt}") for fmt in formats]
        keyboard = InlineKeyboardMarkup([row])

    if details.get("cover_url"):
        try:
            msg = await update.message.reply_photo(
                photo=details["cover_url"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить обложку по URL: {e}")
            msg = await update.message.reply_text(
                text=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    else:
        msg = await update.message.reply_text(
            text=caption,
            parse_mode="HTML",
            reply_markup=keyboard
        )
    return msg.message_id

async def choose_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает выбор формата книги пользователем и отправляет файл книги.

    :param update: Объект обновления Telegram.
    :param context: Контекст выполнения.
    """
    await set_upload_document_action(update, context)
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.exception(f"Ошибка при вызове query.answer(): {e}")

    data = query.data
    parts = data.split("|")

    if len(parts) != 3 or parts[0] != "choose_format":
        logger.error(f"Некорректные данные в callback: {data}")
        if query.message:
            try:
                await query.message.reply_text("Получены некорректные данные. Пожалуйста, попробуйте снова.")
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение об ошибке пользователю: {e}")
        return

    _, book_id, fmt = parts

    try:
        logger.info(f"Начало операции скачивания книги (inline) для book_id {book_id}")
        file_data = await run_with_periodic_action(
            download_book(book_id, fmt),
            update,
            context,
            action=ChatAction.UPLOAD_DOCUMENT,
            interval=4
        )
        if not file_data:
            raise ValueError("Файл книги пуст или не загружен.")
        logger.info(f"Операция скачивания книги (inline) завершена для book_id {book_id}")
    except Exception as e:
        logger.exception(f"Ошибка при скачивании книги {book_id} в формате {fmt}: {e}")
        await query.message.reply_text("Ошибка скачивания книги.")
        return

    try:
        logger.info(f"Начало операции получения деталей книги (inline) для book_id {book_id}")
        details = await run_with_periodic_action(
            get_book_details(book_id),
            update,
            context,
            action=ChatAction.UPLOAD_DOCUMENT,
            interval=4
        )
        logger.info(f"Операция получения деталей книги (inline) завершена для book_id {book_id}")
    except Exception as e:
        logger.exception(f"Ошибка при получении деталей книги для book_id {book_id}: {e}")
        details = {"title": f"book_{book_id}", "author": ""}

    title = details.get("title", "Без названия")
    author = details.get("author", "Неизвестен")
    caption = f"{title[:50]}\nАвтор: {author}"

    try:
        user_settings = await get_user_settings(query.from_user.id)
        naming = user_settings.get("preferred_book_naming", "title_author")
    except Exception as e:
        logger.warning(f"Не удалось получить настройки пользователя: {e}")
        naming = "title_author"

    shortened_title = shorten_title(title, MAX_TITLE_LENGTH)

    name_options = {
        "title": f"{shortened_title}",
        "title_id": f"{shortened_title}_{book_id}",
        "title_author": f"{shortened_title}_{author}",
        "title_author_id": f"{shortened_title}_{author}_{book_id}"
    }
    fname = name_options.get(naming, f"{shortened_title}_{author}")

    try:
        filename = f"{sanitize_filename(fname)}.{fmt}"
    except Exception as e:
        logger.warning(f"Ошибка при обработке имени файла '{fname}': {e}")
        filename = f"book_{book_id}.{fmt}"

    chat_id = query.message.chat.id
    try:
        await context.bot.send_document(chat_id=chat_id, document=file_data, filename=filename, caption=caption)
    except Exception as e:
        logger.exception(f"Ошибка при отправке файла {filename} пользователю {chat_id}: {e}")
        try:
            await query.message.reply_text("Ошибка при отправке файла.")
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение об ошибке пользователю {chat_id}: {e}")