#search.py

from telegram import Update
from telegram.ext import ContextTypes
from utils.chat_actions import set_typing_action
from utils.state import set_user_ephemeral_mode

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    set_user_ephemeral_mode(update.effective_user.id, "general")
    await update.message.reply_text("Следующий поиск будет «общим» (однократно).")
