#settings.py

import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
)
from services.db import get_user_settings, set_user_settings
from utils.chat_actions import set_typing_action

logger = logging.getLogger(__name__)

SETTINGS_MENU, FORMAT_MENU, MODE_MENU, BOOK_NAMING_MENU = range(4)

# ==================================================================
# /settings (ConversationHandler)
# ==================================================================
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    await show_main_settings_menu(update.effective_user.id, update)
    return SETTINGS_MENU

async def show_main_settings_menu(user_id: int, update_or_query):
    st = await get_user_settings(user_id)
    fm = st["preferred_format"] or ""
    md = st["preferred_search_mode"] or "general"
    nb = st.get("preferred_book_naming") or "title_author"
    naming_display = {
        "title": "Название книги.формат",
        "title_id": "Название книги_ID.формат",
        "title_author": "Название книги_Имя автора.формат",
        "title_author_id": "Название книги_Имя автора_ID.формат"
    }
    nb_disp = naming_display.get(nb, "Название книги_Имя автора.формат")
    
    text = (
        "НАСТРОЙКИ:\n\n"
        f"Формат: {fm if fm else 'спрашивать'}\n"
        f"Режим: {md if md!='general' else 'общий'}\n"
        f"Названия книг: {nb_disp}\n\n"
        "Выберите, что меняем:"
    )
    kb = [
        [InlineKeyboardButton("Формат", callback_data="settings_format")],
        [InlineKeyboardButton("Режим поиска", callback_data="settings_mode")],
        [InlineKeyboardButton("Названия книг", callback_data="settings_book_naming")],
    ]
    markup = InlineKeyboardMarkup(kb)
    if getattr(update_or_query, "callback_query", None):
        query = update_or_query.callback_query
        old_text = query.message.text or ""
        if old_text.strip() == text.strip():
            await query.answer("Без изменений")
            return
        await query.edit_message_text(text, reply_markup=markup)
    else:
        await update_or_query.message.reply_text(text, reply_markup=markup)

async def settings_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "settings_format":
        await show_format_menu(query.from_user.id, query)
        return FORMAT_MENU
    elif data == "settings_mode":
        await show_mode_menu(query.from_user.id, query)
        return MODE_MENU
    elif data == "settings_book_naming":
        await show_book_naming_menu(query.from_user.id, query)
        return BOOK_NAMING_MENU
    return SETTINGS_MENU

async def show_book_naming_menu(user_id: int, query):
    st = await get_user_settings(user_id)
    current = st.get("preferred_book_naming") or "title_author"
    naming_options = [
        ("Название книги.формат", "title"),
        ("Название книги_ID.формат", "title_id"),
        ("Название книги_Имя автора.формат", "title_author"),
        ("Название книги_Имя автора_ID.формат", "title_author_id"),
    ]
    text_top = f"Названия книг. Текущий: " \
               f"{dict(naming_options).get(current, 'Название книги_Имя автора.формат')}\nВыберите вариант:"
    kb = []
    for display_text, val in naming_options:
        btn_text = f"🔘 {display_text}" if current == val else display_text
        kb.append([InlineKeyboardButton(btn_text, callback_data=f"set_book_naming|{val}")])
    kb.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
    await query.edit_message_text(text_top, reply_markup=InlineKeyboardMarkup(kb))

async def settings_book_naming_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data.startswith("set_book_naming|"):
        val = data.split("|")[1]
        await set_user_settings(user_id, preferred_book_naming=val)
        await show_book_naming_menu(user_id, query)
        return BOOK_NAMING_MENU
    elif data == "back_to_main":
        await show_main_settings_menu(user_id, update)
        return SETTINGS_MENU
    return BOOK_NAMING_MENU

async def show_format_menu(user_id: int, query):
    st = await get_user_settings(user_id)
    sel = st["preferred_format"] or "ask"
    display_val = "спрашивать" if sel == "ask" else sel
    text_top = f"Формат. Текущий: {display_val}\nВыберите формат:"
    arr = ["спрашивать", "fb2", "epub", "mobi", "pdf"]
    kb = []
    for opt in arr:
        val = "ask" if opt == "спрашивать" else opt
        text_btn = f"🔘 {opt}" if val == sel else opt
        kb.append([InlineKeyboardButton(text_btn, callback_data=f"set_fmt|{opt}")])
    kb.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
    await query.edit_message_text(text_top, reply_markup=InlineKeyboardMarkup(kb))

async def show_mode_menu(user_id: int, query):
    st = await get_user_settings(user_id)
    sel = st["preferred_search_mode"] or "general"
    text_top = f"Режим. Текущий: {sel if sel!='general' else 'общий'}\nВыберите режим:"
    modes = [("общий", "general"), ("только книги", "book"), ("только авторы", "author")]
    kb = []
    for (title, val) in modes:
        tbtn = f"🔘 {title}" if val == sel else title
        kb.append([InlineKeyboardButton(tbtn, callback_data=f"set_mode|{val}")])
    kb.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
    old_text = query.message.text or ""
    if old_text.strip() == text_top.strip():
        await query.answer("Без изменений")
        return
    await query.edit_message_text(text_top, reply_markup=InlineKeyboardMarkup(kb))

async def settings_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data.startswith("set_fmt|"):
        val = data.split("|")[1]
        new_val = "ask" if val == "спрашивать" else val
        await set_user_settings(user_id, preferred_format=new_val)
        await show_format_menu(user_id, query)
        return FORMAT_MENU
    elif data == "back_to_main":
        await show_main_settings_menu(user_id, update)
        return SETTINGS_MENU
    return FORMAT_MENU

async def settings_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if data.startswith("set_mode|"):
        val = data.split("|")[1]
        await set_user_settings(user_id, preferred_search_mode=val)
        await show_mode_menu(user_id, query)
        return MODE_MENU
    elif data == "back_to_main":
        await show_main_settings_menu(user_id, update)
        return SETTINGS_MENU
    return MODE_MENU

def get_settings_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(settings_main_menu_callback, pattern=r"^(settings_format|settings_mode|settings_book_naming)$")
            ],
            FORMAT_MENU: [
                CallbackQueryHandler(settings_format_callback, pattern=r"^(set_fmt\|.*|back_to_main)$")
            ],
            MODE_MENU: [
                CallbackQueryHandler(settings_mode_callback, pattern=r"^(set_mode\|.*|back_to_main)$")
            ],
            BOOK_NAMING_MENU: [
                CallbackQueryHandler(settings_book_naming_callback, pattern=r"^(set_book_naming\|.*|back_to_main)$")
            ],
        },
        fallbacks=[],
        allow_reentry=True,
        per_message=False
    )
