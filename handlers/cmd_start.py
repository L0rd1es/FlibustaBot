# handlers/cmd_start.py

import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет приветственное сообщение с перечнем доступных команд.
    """
    user = update.effective_user
    user_id = user.id if user else "unknown"

    try:
        logger.info("Пользователь %s вызвал команду /start", user_id)
        await set_typing_action(update, context)

        start_text = (
            "<b>Привет! Я бот для поиска книг на Флибусте.</b>\n"
            "━━━━━━━━━━━━━\n\n"
            "Просто напиши в чат <u>название книги</u> или <u>имя автора</u>, и я поищу!\n\n"
            "<b>Доступные команды:</b>\n"
            "• <b>Настройки:</b> <i>/settings</i>\n"
            "• <b>Общий поиск:</b> <i>/search</i>\n"
            "• <b>Поиск книг:</b> <i>/book</i>\n"
            "• <b>Поиск авторов:</b> <i>/author</i>\n\n"
            "━━━━━━━━━━━━━"
        )

        if update.message:
            return await update.message.reply_text(start_text, parse_mode="HTML")
        else:
            logger.warning("Не удалось отправить /start пользователю %s: в update нет message", user_id)

    except Exception:
        logger.exception("Ошибка в команде /start для пользователя %s", user_id)
        if update.message:
            return await update.message.reply_text(
                "Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова."
            )
