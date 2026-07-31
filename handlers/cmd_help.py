import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action

logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отправляет сообщение с перечнем доступных команд и их описанием.
    """
    user = update.effective_user
    user_id = user.id if user else 0

    try:
        logger.info("Пользователь %s вызвал команду /help", user_id)
        await set_typing_action(update, context)

        help_text = (
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
            await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
        elif update.effective_chat:
            # fallback, если help вызван в другом контексте
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=help_text,
                parse_mode=ParseMode.HTML,
            )
        else:
            logger.warning("Нет message и chat_id для ответа пользователю %s", user_id)

    except Exception as e:
        logger.exception("Ошибка в команде /help для пользователя %s: %s", user_id, e)
        error_msg = "Произошла ошибка при обработке команды. Пожалуйста, попробуйте снова."
        if update.message:
            await update.message.reply_text(error_msg)
        elif update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=error_msg)
