import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action
from utils.state import set_user_ephemeral_mode

logger = logging.getLogger(__name__)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Переключает бота в режим общего поиска для следующего запроса.

    :param update: Объект обновления Telegram.
    :param context: Контекст выполнения.
    """
    user_id = update.effective_user.id
    try:
        logger.info(f"Пользователь {user_id} вызвал команду /search")
        await set_typing_action(update, context)
        set_user_ephemeral_mode(user_id, "general")
        if update.message:
            await update.message.reply_text("Следующий поиск будет «общим» (однократно).")
        else:
            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: отсутствует объект message в update.")
    except Exception as e:
        logger.error(f"Ошибка в команде /search для пользователя {user_id}: {e}")
        if update.message:
            await update.message.reply_text("Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова.")
        else:
            logger.warning(f"Не удалось отправить сообщение об ошибке пользователю {user_id}: отсутствует объект message в update.")
