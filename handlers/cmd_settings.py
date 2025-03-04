import logging
from enum import Enum, auto
from typing import Optional, Union

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
)
from services.db import get_user_settings, set_user_settings
from utils.chat_actions import set_typing_action

logger = logging.getLogger(__name__)

class SettingsState(Enum):
    MAIN_MENU = auto()
    FORMAT_MENU = auto()
    MODE_MENU = auto()
    BOOK_NAMING_MENU = auto()

CALLBACK_SETTINGS_FORMAT = "settings_format"
CALLBACK_SETTINGS_MODE = "settings_mode"
CALLBACK_SETTINGS_BOOK_NAMING = "settings_book_naming"
CALLBACK_SET_FMT = "set_fmt"
CALLBACK_SET_MODE = "set_mode"
CALLBACK_SET_BOOK_NAMING = "set_book_naming"
CALLBACK_BACK_TO_MAIN = "back_to_main"

def build_inline_keyboard(buttons: list[list[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    """
    Формирует и возвращает объект InlineKeyboardMarkup из списка кнопок.
    """
    return InlineKeyboardMarkup(buttons)

async def send_or_edit_message(
    update_or_query: Union[Update, CallbackQuery],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """
    Отправляет сообщение пользователю: если получен объект Update – отправляет новое сообщение,
    если получен CallbackQuery – редактирует сообщение.
    """
    if hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
        query: CallbackQuery = update_or_query.callback_query
        await query.edit_message_text(text, reply_markup=reply_markup)
    elif isinstance(update_or_query, CallbackQuery):
        await update_or_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update_or_query.message.reply_text(text, reply_markup=reply_markup)

async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик команды /settings.
    """
    await set_typing_action(update, context)
    await show_main_settings_menu(update.effective_user.id, update)
    return SettingsState.MAIN_MENU.value

async def show_main_settings_menu(user_id: int, update_or_query: Union[Update, CallbackQuery]) -> None:
    """
    Отображает главное меню настроек.
    """
    try:
        user_settings = await get_user_settings(user_id)
    except Exception as e:
        logger.error(f"Ошибка получения настроек для пользователя {user_id}: {e}")
        user_settings = {}

    preferred_format = user_settings.get("preferred_format") or ""
    preferred_search_mode = user_settings.get("preferred_search_mode") or "general"
    preferred_book_naming = user_settings.get("preferred_book_naming") or "title_author"
    
    naming_display = {
        "title": "Название книги.формат",
        "title_id": "Название книги_ID.формат",
        "title_author": "Название книги_Имя автора.формат",
        "title_author_id": "Название книги_Имя автора_ID.формат",
    }
    book_naming_display = naming_display.get(preferred_book_naming, "Название книги_Имя автора.формат")

    text = (
        "НАСТРОЙКИ:\n\n"
        f"Формат: {preferred_format if preferred_format else 'спрашивать'}\n"
        f"Режим: {preferred_search_mode if preferred_search_mode != 'general' else 'общий'}\n"
        f"Названия книг: {book_naming_display}\n\n"
        "Выберите, что меняем:"
    )
    keyboard = [
        [InlineKeyboardButton("Формат", callback_data=CALLBACK_SETTINGS_FORMAT)],
        [InlineKeyboardButton("Режим поиска", callback_data=CALLBACK_SETTINGS_MODE)],
        [InlineKeyboardButton("Названия книг", callback_data=CALLBACK_SETTINGS_BOOK_NAMING)],
    ]
    markup = build_inline_keyboard(keyboard)

    if hasattr(update_or_query, "callback_query") and update_or_query.callback_query:
        query: CallbackQuery = update_or_query.callback_query
        old_text = query.message.text or ""
        if old_text.strip() == text.strip():
            await query.answer("Без изменений")
            return

    await send_or_edit_message(update_or_query, text, reply_markup=markup)

async def settings_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора пункта в главном меню настроек.
    """
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == CALLBACK_SETTINGS_FORMAT:
        await show_format_menu(query.from_user.id, query)
        return SettingsState.FORMAT_MENU.value
    elif data == CALLBACK_SETTINGS_MODE:
        await show_mode_menu(query.from_user.id, query)
        return SettingsState.MODE_MENU.value
    elif data == CALLBACK_SETTINGS_BOOK_NAMING:
        await show_book_naming_menu(query.from_user.id, query)
        return SettingsState.BOOK_NAMING_MENU.value
    return SettingsState.MAIN_MENU.value

async def show_book_naming_menu(user_id: int, query: CallbackQuery) -> None:
    """
    Отображает меню выбора формата названия книги.
    """
    try:
        user_settings = await get_user_settings(user_id)
    except Exception as e:
        logger.error(f"Ошибка получения настроек для пользователя {user_id}: {e}")
        user_settings = {}
    current_naming = user_settings.get("preferred_book_naming") or "title_author"
    naming_options = [
        ("Название книги.формат", "title"),
        ("Название книги_ID.формат", "title_id"),
        ("Название книги_Имя автора.формат", "title_author"),
        ("Название книги_Имя автора_ID.формат", "title_author_id"),
    ]
    current_display = dict(naming_options).get(current_naming, "Название книги_Имя автора.формат")
    text_top = f"Названия книг. Текущий: {current_display}\nВыберите вариант:"
    keyboard = []
    for display_text, option_value in naming_options:
        button_text = f"🔘 {display_text}" if current_naming == option_value else display_text
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_SET_BOOK_NAMING}|{option_value}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data=CALLBACK_BACK_TO_MAIN)])
    markup = build_inline_keyboard(keyboard)
    try:
        await query.edit_message_text(text_top, reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения для book naming: {e}")

async def settings_book_naming_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора формата названия книги.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith(f"{CALLBACK_SET_BOOK_NAMING}|"):
        option_value = data.split("|", 1)[1]
        try:
            await set_user_settings(user_id, preferred_book_naming=option_value)
        except Exception as e:
            logger.error(f"Ошибка сохранения настройки названия книг для пользователя {user_id}: {e}")
        await show_book_naming_menu(user_id, query)
        return SettingsState.BOOK_NAMING_MENU.value
    elif data == CALLBACK_BACK_TO_MAIN:
        await show_main_settings_menu(user_id, update)
        return SettingsState.MAIN_MENU.value

    return SettingsState.BOOK_NAMING_MENU.value

async def show_format_menu(user_id: int, query: CallbackQuery) -> None:
    """
    Отображает меню выбора формата.
    """
    try:
        user_settings = await get_user_settings(user_id)
    except Exception as e:
        logger.error(f"Ошибка получения настроек для пользователя {user_id}: {e}")
        user_settings = {}
    selected_format = user_settings.get("preferred_format") or "ask"
    display_value = "спрашивать" if selected_format == "ask" else selected_format
    text_top = f"Формат. Текущий: {display_value}\nВыберите формат:"
    format_options = ["спрашивать", "fb2", "epub", "mobi", "pdf"]
    keyboard = []
    for option in format_options:
        option_value = "ask" if option == "спрашивать" else option
        button_text = f"🔘 {option}" if option_value == selected_format else option
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_SET_FMT}|{option}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data=CALLBACK_BACK_TO_MAIN)])
    markup = build_inline_keyboard(keyboard)
    try:
        await query.edit_message_text(text_top, reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения для формата: {e}")

async def show_mode_menu(user_id: int, query: CallbackQuery) -> None:
    """
    Отображает меню выбора режима поиска.
    """
    try:
        user_settings = await get_user_settings(user_id)
    except Exception as e:
        logger.error(f"Ошибка получения настроек для пользователя {user_id}: {e}")
        user_settings = {}
    selected_mode = user_settings.get("preferred_search_mode") or "general"
    text_top = f"Режим. Текущий: {selected_mode if selected_mode != 'general' else 'общий'}\nВыберите режим:"
    mode_options = [("общий", "general"), ("только книги", "book"), ("только авторы", "author")]
    keyboard = []
    for display_text, option_value in mode_options:
        button_text = f"🔘 {display_text}" if option_value == selected_mode else display_text
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"{CALLBACK_SET_MODE}|{option_value}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data=CALLBACK_BACK_TO_MAIN)])
    markup = build_inline_keyboard(keyboard)

    old_text = query.message.text or ""
    if old_text.strip() == text_top.strip():
        await query.answer("Без изменений")
        return

    try:
        await query.edit_message_text(text_top, reply_markup=markup)
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения для режима поиска: {e}")

async def settings_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора формата.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith(f"{CALLBACK_SET_FMT}|"):
        option_value = data.split("|", 1)[1]
        new_format = "ask" if option_value == "спрашивать" else option_value
        try:
            await set_user_settings(user_id, preferred_format=new_format)
        except Exception as e:
            logger.error(f"Ошибка сохранения формата для пользователя {user_id}: {e}")
        await show_format_menu(user_id, query)
        return SettingsState.FORMAT_MENU.value
    elif data == CALLBACK_BACK_TO_MAIN:
        await show_main_settings_menu(user_id, update)
        return SettingsState.MAIN_MENU.value

    return SettingsState.FORMAT_MENU.value

async def settings_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Обработчик выбора режима поиска.
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith(f"{CALLBACK_SET_MODE}|"):
        option_value = data.split("|", 1)[1]
        try:
            await set_user_settings(user_id, preferred_search_mode=option_value)
        except Exception as e:
            logger.error(f"Ошибка сохранения режима поиска для пользователя {user_id}: {e}")
        await show_mode_menu(user_id, query)
        return SettingsState.MODE_MENU.value
    elif data == CALLBACK_BACK_TO_MAIN:
        await show_main_settings_menu(user_id, update)
        return SettingsState.MAIN_MENU.value

    return SettingsState.MODE_MENU.value

def get_settings_conversation_handler() -> ConversationHandler:
    """
    Возвращает ConversationHandler для команды /settings.
    """
    return ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            SettingsState.MAIN_MENU.value: [
                CallbackQueryHandler(
                    settings_main_menu_callback,
                    pattern=f"^({CALLBACK_SETTINGS_FORMAT}|{CALLBACK_SETTINGS_MODE}|{CALLBACK_SETTINGS_BOOK_NAMING})$",
                )
            ],
            SettingsState.FORMAT_MENU.value: [
                CallbackQueryHandler(
                    settings_format_callback, pattern=f"^({CALLBACK_SET_FMT}\|.*|{CALLBACK_BACK_TO_MAIN})$"
                )
            ],
            SettingsState.MODE_MENU.value: [
                CallbackQueryHandler(
                    settings_mode_callback, pattern=f"^({CALLBACK_SET_MODE}\|.*|{CALLBACK_BACK_TO_MAIN})$"
                )
            ],
            SettingsState.BOOK_NAMING_MENU.value: [
                CallbackQueryHandler(
                    settings_book_naming_callback, pattern=f"^({CALLBACK_SET_BOOK_NAMING}\|.*|{CALLBACK_BACK_TO_MAIN})$"
                )
            ],
        },
        fallbacks=[],
        allow_reentry=True,
        per_message=False,
    )
