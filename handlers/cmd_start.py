#start.py

import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет приветственное сообщение с перечнем доступных команд.

    :param update: Объект обновления Telegram.
    :param context: Контекст выполнения.
    """
    user_id = update.effective_user.id
    try:
        logger.info(f"Пользователь {user_id} вызвал команду /start")
        await set_typing_action(update, context)

        start_text = (
            "<b>Привет! Я бот для поиска книг на Флибусте.</b>\n"
            "━━━━━━━━━━━━━\n\n"
            "Просто напиши в чат <u>название книги</u> или <u>имя автора</u> и я поищу!\n\n"
            "<b>Доступные команды:</b>\n"
            "• <b>Настройки:</b> <i>/settings</i>\n"
            "• <b>Общий поиск:</b> <i>/search</i>\n"
            "• <b>Поиск книг:</b> <i>/book</i>\n"
            "• <b>Поиск авторов:</b> <i>/author</i>\n\n"
            "━━━━━━━━━━━━━"
        )
        if update.message:
            await update.message.reply_text(start_text, parse_mode="HTML")
        else:
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: отсутствует объект message в update.")
    except Exception as e:
        logger.error(f"Ошибка в команде /start для пользователя {user_id}: {e}")
        if update.message:
            await update.message.reply_text("Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова.")
        else:
            logger.warning(f"Не удалось отправить сообщение об ошибке пользователю {user_id}: отсутствует объект message в update.")
