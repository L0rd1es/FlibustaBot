# main.py

import logging
import asyncio
import sys
import os
import html
import json
import traceback

import nest_asyncio
nest_asyncio.apply()

from dotenv import load_dotenv
load_dotenv()

from datetime import datetime, timedelta
from logging.handlers import TimedRotatingFileHandler

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from config import (
    ADMIN_ID,
    LOG_FILE,
    STATS_FILE,
    SEND_REPORT_TIME,
)
from db import init_db
from service import init_session

from handlers import (
    start_command,
    help_command,
    search_command,
    book_command,
    author_command,
    text_message_handler,
    choose_format_callback,
    no_op_callback,
    get_settings_conversation_handler,

    # Пагинация результатов
    pagination_callback_handler,
)

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Настройка TimedRotatingFileHandler для ротации логов каждый час
    fh = TimedRotatingFileHandler(LOG_FILE, when="H", interval=1, backupCount=24, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


async def send_logs_to_admin(context):
    """Отправка LOG_FILE и STATS_FILE админу по расписанию."""
    app = context.application
    try:
        if os.path.exists(LOG_FILE):
            await app.bot.send_document(
                chat_id=ADMIN_ID,
                document=open(LOG_FILE, "rb"),
                filename=os.path.basename(LOG_FILE),
                caption="Логи за период"
            )
        if os.path.exists(STATS_FILE):
            await app.bot.send_document(
                chat_id=ADMIN_ID,
                document=open(STATS_FILE, "rb"),
                filename=os.path.basename(STATS_FILE),
                caption="Статистика за период"
            )
    except Exception as e:
        logging.error(f"Не удалось отправить файлы админу: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирование ошибок и отправка сообщения админу."""
    logger = logging.getLogger(__name__)
    logger.error("Исключение при обработке обновления:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "Возникло исключение при обработке обновления\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение админу: {e}")

async def main_async():
    setup_logging()
    logging.info("Инициализация БД...")
    await init_db()
    await init_session() 

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN (см. .env или config).")

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    from telegram import BotCommand
    bot_commands = [
        BotCommand("start", "Начало"),
        BotCommand("help", "Справка"),
        BotCommand("settings", "Настройки"),
        BotCommand("search", "Один раз общий поиск"),
        BotCommand("book", "Один раз поиск по книгам"),
        BotCommand("author", "Один раз поиск по авторам"),
    ]
    await application.bot.set_my_commands(bot_commands)

    # ConversationHandler для /settings
    settings_conv = get_settings_conversation_handler()
    application.add_handler(settings_conv)

    # Остальные команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("book", book_command))
    application.add_handler(CommandHandler("author", author_command))

    # Пагинация (перелистывание)
    application.add_handler(CallbackQueryHandler(pagination_callback_handler, pattern=r"^pagination\|.*"))

    # Inline-кнопки для скачивания
    application.add_handler(CallbackQueryHandler(choose_format_callback, pattern=r"^choose_format\|"))
    application.add_handler(CallbackQueryHandler(no_op_callback, pattern=r"^no-op$"))

    # Текстовые (включая /downloadXXX, /authorXXX, обычный поиск)
    application.add_handler(MessageHandler(filters.TEXT | filters.COMMAND, text_message_handler))

    # Планируем отправку логов админу
    try:
        hh, mm = SEND_REPORT_TIME.split(":")
        hour = int(hh)
        minute = int(mm)
    except:
        logging.warning(f"Неверный формат SEND_REPORT_TIME={SEND_REPORT_TIME}, используем 3:00")
        hour, minute = 3, 0

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        send_logs_to_admin,
        trigger="cron",
        hour=hour,
        minute=minute,
        args=[application],
    )
    scheduler.start()

    logging.info("Запуск бота...")
    await application.run_polling()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
