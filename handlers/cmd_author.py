# handlers/cmd_author.py

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action
from utils.state import set_user_ephemeral_mode

logger = logging.getLogger(__name__)

async def author_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Переключает бота в режим поиска по авторам для следующего запроса (однократно).
    """
    user = update.effective_user
    user_id = user.id if user else 0

    try:
        logger.info("Пользователь %s вызвал команду /author", user_id)
        await set_typing_action(update, context)

        set_user_ephemeral_mode(user_id, "author")

        text = "Следующий поиск будет <b>только по авторам</b> <i>(однократно)</i>."

        if update.message:
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        elif update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=text,
                parse_mode=ParseMode.HTML,
            )
        else:
            logger.warning("Нет message и chat_id для ответа пользователю %s", user_id)

    except Exception as e:
        logger.exception("Ошибка в команде /author для пользователя %s: %s", user_id, e)
        err = "Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова."
        if update.message:
            await update.message.reply_text(err)
        elif update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=err)
