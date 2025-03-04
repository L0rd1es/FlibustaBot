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
            "Привет! Я бот для поиска книг на Флибусте.\n\n"
            "Команды:\n"
            "/search - Общий поиск (1 раз)\n"
            "/book - Поиск книг (1 раз)\n"
            "/author - Поиск авторов (1 раз)\n"
            "/settings - Настройки формата/режима\n\n"
            "Просто введи запрос...\n"
            "Скачать: /download123\n"
            "Автор: /author123\n"
        )
        if update.message:
            await update.message.reply_text(start_text)
        else:
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: отсутствует объект message в update.")
    except Exception as e:
        logger.error(f"Ошибка в команде /start для пользователя {user_id}: {e}")
        if update.message:
            await update.message.reply_text("Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова.")
        else:
            logger.warning(f"Не удалось отправить сообщение об ошибке пользователю {user_id}: отсутствует объект message в update.")
