import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action
from utils.state import set_user_ephemeral_mode

logger = logging.getLogger(__name__)

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Переключает бота в режим «общего» поиска для следующего запроса (однократно).
    """
    user = update.effective_user
    user_id = user.id if user else 0

    try:
        logger.info("Пользователь %s вызвал команду /search", user_id)
        await set_typing_action(update, context)

        # Если в set_user_ephemeral_mode вы уже добавили timestamp — просто передаём строку режима.
        # Если нет — можно расширить сигнатуру функции в state.py, но это необязательно.
        set_user_ephemeral_mode(user_id, "general")

        msg = (
            "Следующий поиск будет «<b>общим</b>» <i>(однократно)</i>."
        )
        if update.message:
            await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
        else:
            # На случай callback-контекста или других апдейтов без message
            chat_id = update.effective_chat.id if update.effective_chat else None
            if chat_id:
                await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode=ParseMode.HTML)
            else:
                logger.warning("Нет chat_id для ответа пользователю %s", user_id)

    except Exception as e:
        logger.exception("Ошибка в /search для пользователя %s: %s", user_id, e)
        if update.message:
            await update.message.reply_text(
                "Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова."
            )
