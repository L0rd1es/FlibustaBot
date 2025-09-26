# main.py

import sys
import os

# Складируем __pycache__ в папку проекта
sys.pycache_prefix = os.path.join(os.path.dirname(__file__), "pycache")

import logging
import asyncio
import html
import json
import traceback
import signal

from dotenv import load_dotenv
load_dotenv()

from logging.handlers import TimedRotatingFileHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, BotCommand
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    AIORateLimiter,  # ⬅️ рейт-лимитер
)

from config import ADMIN_ID, LOG_FILE, STATS_FILE, SEND_REPORT_TIME
from services.db import init_db
from services.service import init_session

from handlers.cmd_settings import get_settings_conversation_handler
from handlers.cmd_search import search_command
from handlers.cmd_author import author_command
from handlers.cmd_start import start_command
from handlers.cmd_help import help_command
from handlers.cmd_book import book_command
from handlers.message_handler import text_message_handler
from handlers.book_handler import choose_format_callback
from utils.pagination import pagination_callback_handler
from utils.utils import no_op_callback
from utils.state import cleanup_old_data
from utils.whitelist import whitelist_required, process_whitelist


def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    logging.getLogger("httpx").setLevel(logging.WARNING)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    fh = TimedRotatingFileHandler(LOG_FILE, when="H", interval=1, backupCount=24, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


# --- Команды для меню (используются в post_init) ---
BOT_COMMANDS = [
    BotCommand("start", "Начало"),
    BotCommand("help", "Справка"),
    BotCommand("settings", "Настройки"),
    BotCommand("search", "Один раз общий поиск"),
    BotCommand("book", "Один раз поиск по книгам"),
    BotCommand("author", "Один раз поиск по авторам"),
]


async def _post_init(app: Application) -> None:
    """Вызывается Application'ом после инициализации — выставляем команды бота."""
    await app.bot.set_my_commands(BOT_COMMANDS)


async def send_logs_to_admin(application: Application):
    """Отправка LOG_FILE и STATS_FILE админу по расписанию (APScheduler передаёт application через args)."""
    bot = application.bot
    try:
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "rb") as log_file:
                await bot.send_document(
                    chat_id=ADMIN_ID,
                    document=log_file,
                    filename=os.path.basename(LOG_FILE),
                    caption="Логи за период"
                )

        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, "rb") as stats_file:
                await bot.send_document(
                    chat_id=ADMIN_ID,
                    document=stats_file,
                    filename=os.path.basename(STATS_FILE),
                    caption="Статистика за период"
                )

    except Exception as e:
        logging.error(f"Не удалось отправить файлы админу: {e}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Логирование ошибок и отправка сообщения админу."""
    logger = logging.getLogger(__name__)
    logger.error("Исключение при обработке обновления:", exc_info=context.error)

    exc = context.error
    if exc is not None:
        tb_list = traceback.format_exception(type(exc), exc, exc.__traceback__)
    else:
        tb_list = ["Нет данных об исключении (context.error is None)."]
    tb_string = "".join(tb_list)

    try:
        update_str = update.to_dict() if isinstance(update, Update) else str(update)
        update_json = html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))
    except Exception:
        update_json = html.escape(str(update))

    message = (
        "Возникло исключение при обработке обновления\n"
        f"<pre>update = {update_json}</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=message, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение админу: {e}")


def main():
    # === Python 3.13 / Windows: один общий event loop для всего процесса ===
    if os.name == "nt":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    setup_logging()
    logging.info("Инициализация БД...")
    loop.run_until_complete(init_db())
    loop.run_until_complete(init_session())

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_TOKEN:
        raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN (см. .env или config).")

    # Немного параллелизма обработчиков + rate limiter + post_init для команд
    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .concurrent_updates(32)
        .rate_limiter(AIORateLimiter())  # ⬅️ включаем рейт-лимитер (дефолтные безопасные лимиты)
        .post_init(_post_init)
        .build()
    )

    # Хендлеры
    settings_conv = get_settings_conversation_handler()
    application.add_handler(settings_conv)

    username_filter = filters.Regex(r'^@\w+$')
    application.add_handler(MessageHandler(username_filter, process_whitelist))

    application.add_handler(CommandHandler("start", whitelist_required(start_command)))
    application.add_handler(CommandHandler("help", whitelist_required(help_command)))
    application.add_handler(CommandHandler("search", whitelist_required(search_command)))
    application.add_handler(CommandHandler("book", whitelist_required(book_command)))
    application.add_handler(CommandHandler("author", whitelist_required(author_command)))

    # Универсальный быстрый обработчик: текст ИЛИ команды
    application.add_handler(MessageHandler(filters.TEXT | filters.COMMAND, whitelist_required(text_message_handler)))

    application.add_handler(CallbackQueryHandler(whitelist_required(pagination_callback_handler), pattern=r"^pagination\|.*"))
    application.add_handler(CallbackQueryHandler(whitelist_required(choose_format_callback), pattern=r"^choose_format\|"))
    application.add_handler(CallbackQueryHandler(no_op_callback, pattern=r"^no-op$"))

    application.add_error_handler(error_handler)

    # --- APScheduler на том же event loop ---
    try:
        hh, mm = SEND_REPORT_TIME.split(":")
        hour = int(hh)
        minute = int(mm)
    except Exception:
        logging.warning(f"Неверный формат SEND_REPORT_TIME={SEND_REPORT_TIME}, используем 3:00 UTC")
        hour, minute = 3, 0

    scheduler = AsyncIOScheduler(timezone="UTC", event_loop=loop)
    scheduler.add_job(send_logs_to_admin, trigger="cron", hour=hour, minute=minute, args=[application])
    scheduler.add_job(cleanup_old_data, trigger="interval", minutes=10)
    scheduler.start()

    # --- Graceful shutdown: корректно гасим планировщик при выходе ---
    def _shutdown_handler(*_):
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

    for sig in ("SIGINT", "SIGTERM"):
        if hasattr(signal, sig):
            try:
                signal.signal(getattr(signal, sig), _shutdown_handler)
            except Exception:
                pass

    logging.info("Запуск бота...")
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],  # берём только то, что реально используем
    )


if __name__ == "__main__":
    main()
