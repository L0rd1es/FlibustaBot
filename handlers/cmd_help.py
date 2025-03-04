#help.py

import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action

logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет сообщение с перечнем доступных команд и их описанием.

    :param update: Объект обновления Telegram.
    :param context: Контекст выполнения.
    """
    user_id = update.effective_user.id
    try:
        logger.info(f"Пользователь {user_id} вызвал команду /help")
        await set_typing_action(update, context)
        help_text = (
            "Помощь:\n"
            "/start - Начало\n"
            "/help - Это сообщение\n"
            "/settings - Настройки\n"
            "/search /book /author - одноразовые режимы\n\n"
            "Скачивание: /download<id>\n"
            "Автор: /author<id>\n"
        )
        if update.message:
            await update.message.reply_text(help_text)
        else:
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: отсутствует объект message в update.")
    except Exception as e:
        logger.error(f"Ошибка в команде /help для пользователя {user_id}: {e}")
        if update.message:
            await update.message.reply_text("Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова.")
        else:
            logger.warning(f"Не удалось отправить сообщение об ошибке пользователю {user_id}: отсутствует объект message в update.")
