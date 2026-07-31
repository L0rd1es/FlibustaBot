# handlers/cmd_settings.py

import logging
import html
import re
from enum import Enum, auto
from typing import Union, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
)

from services.db import get_user_settings, set_user_settings
from utils.chat_actions import set_typing_action
from utils.utils import send_or_edit_message

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


def build_inline_keyboard(buttons: List[List[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    """Формирует инлайн-клавиатуру из матрицы кнопок."""
    return InlineKeyboardMarkup(buttons)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /settings: показываем главное меню настроек."""
    await set_typing_action(update, context)
    user = update.effective_user
    user_id = user.id if user else 0
    await show_main_settings_menu(user_id, update)
    return SettingsState.MAIN_MENU.value


async def show_main_settings_menu(user_id: int, target: Union[Update, CallbackQuery]) -> None:
    """Главное меню настроек."""
    try:
        user_settings = await get_user_settings(user_id)
    except Exception:
        logger.exception("Ошибка получения настроек пользователя %s", user_id)
        user_settings = {}

    preferred_format = user_settings.get("preferred_format") or ""
    display_format = "спрашивать" if preferred_format in ("", "ask") else preferred_format

    preferred_search_mode = user_settings.get("preferred_search_mode") or "general"
    mode_options = [("общий", "general"), ("только книги", "book"), ("только авторы", "author")]
    display_search_mode = next((text for text, mode in mode_options if mode == preferred_search_mode),
                               preferred_search_mode)

    preferred_book_naming = user_settings.get("preferred_book_naming") or "title_author"
    naming_display = {
        "title": "Название_книги.формат",
        "title_id": "Название_книги_ID.формат",
        "title_author": "Название_книги_Имя_автора.формат",
        "title_author_id": "Название_книги_Имя_автора_ID.формат",
    }
    book_naming_display = naming_display.get(preferred_book_naming, "Название_книги_Имя_автора.формат")

    text = (
        "📌 <b>Настройки</b>\n"
        "━━━━━━━━━━━━━\n\n"
        f"<b>Предпочитаемый формат:</b>\n <code>{html.escape(display_format)}</code>\n\n"
        f"<b>Режим поиска:</b>\n <code>{html.escape(display_search_mode)}</code>\n\n"
        f"<b>Нейминг книг:</b>\n <code>{html.escape(book_naming_display)}</code>\n\n"
        "━━━━━━━━━━━━━\n"
        "<b>Выберите, что меняем:</b>"
    )

    keyboard = [
        [InlineKeyboardButton("Формат", callback_data=CALLBACK_SETTINGS_FORMAT)],
        [InlineKeyboardButton("Режим поиска", callback_data=CALLBACK_SETTINGS_MODE)],
        [InlineKeyboardButton("Названия книг", callback_data=CALLBACK_SETTINGS_BOOK_NAMING)],
    ]
    markup = build_inline_keyboard(keyboard)

    await send_or_edit_message(target, text, reply_markup=markup)


# ---------- Book naming ----------

async def show_book_naming_menu(
    user_id: int,
    target: Union[CallbackQuery, Update],
    force_value: Optional[str] = None,
) -> None:
    """Меню выбора схемы имени файла книги."""
    try:
        user_settings = await get_user_settings(user_id)
    except Exception:
        logger.exception("Ошибка получения настроек пользователя %s", user_id)
        user_settings = {}

    current_naming = force_value or user_settings.get("preferred_book_naming") or "title_author"

    naming_options = [
        ("Название книги.формат", "title"),
        ("Название книги_ID.формат", "title_id"),
        ("Название книги_Имя автора.формат", "title_author"),
        ("Название книги_Имя автора_ID.формат", "title_author_id"),
    ]
    naming_mapping = {option_value: display_text for display_text, option_value in naming_options}
    current_display = naming_mapping.get(current_naming, "Название книги_Имя автора.формат")

    text_top = (
        "📌 <b>Настройки</b>\n"
        "━━━━━━━━━━━━━\n\n"
        "<b>Нейминг книг.</b>\n\n"
        "<b>Текущий:</b>\n"
        f"<code>{html.escape(current_display)}</code>\n\n"
        "━━━━━━━━━━━━━\n"
        "<b>Выберите, что меняем:</b>"
    )

    keyboard = []
    for display_text, option_value in naming_options:
        is_current = (current_naming == option_value)
        caption = f"🔘 {display_text}" if is_current else display_text
        keyboard.append([InlineKeyboardButton(caption, callback_data=f"{CALLBACK_SET_BOOK_NAMING}|{option_value}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data=CALLBACK_BACK_TO_MAIN)])

    await send_or_edit_message(target, text_top, reply_markup=build_inline_keyboard(keyboard))


async def settings_book_naming_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик клика по пунктам меню «Нейминг книг»."""
    query = update.callback_query
    if query is None:
        logger.warning("settings_book_naming_callback: callback_query is None")
        return SettingsState.BOOK_NAMING_MENU.value

    await query.answer()
    data = query.data or ""
    uid = query.from_user.id

    if data.startswith(f"{CALLBACK_SET_BOOK_NAMING}|"):
        option_value = data.split("|", 1)[1]
        try:
            await set_user_settings(uid, preferred_book_naming=option_value)
        except Exception:
            logger.exception("Ошибка сохранения naming для пользователя %s", uid)

        # Рендерим сразу выбранное значение
        await show_book_naming_menu(uid, query, force_value=option_value)
        return SettingsState.BOOK_NAMING_MENU.value

    if data == CALLBACK_BACK_TO_MAIN:
        await show_main_settings_menu(uid, update)
        return SettingsState.MAIN_MENU.value

    return SettingsState.BOOK_NAMING_MENU.value


# ---------- Format ----------

async def show_format_menu(
    user_id: int,
    target: Union[CallbackQuery, Update],
    force_value: Optional[str] = None,
) -> None:
    """Меню выбора предпочитаемого формата."""
    try:
        user_settings = await get_user_settings(user_id)
    except Exception:
        logger.exception("Ошибка получения настроек пользователя %s", user_id)
        user_settings = {}

    selected_format = force_value or user_settings.get("preferred_format") or "ask"
    display_value = "спрашивать" if selected_format == "ask" else selected_format

    text_top = (
        "📌 <b>Настройки</b>\n"
        "━━━━━━━━━━━━━\n\n"
        "<b>Предпочитаемый формат.</b>\n\n"
        "<b>Текущий:</b>\n"
        f"<code>{html.escape(display_value)}</code>\n\n"
        "━━━━━━━━━━━━━\n"
        "<b>Выберите, что меняем:</b>"
    )

    format_options = ["спрашивать", "fb2", "epub", "mobi", "pdf"]
    keyboard = []
    for option in format_options:
        option_value = "ask" if option == "спрашивать" else option
        is_current = (option_value == selected_format)
        caption = f"🔘 {option}" if is_current else option
        keyboard.append([InlineKeyboardButton(caption, callback_data=f"{CALLBACK_SET_FMT}|{option}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data=CALLBACK_BACK_TO_MAIN)])

    await send_or_edit_message(target, text_top, reply_markup=build_inline_keyboard(keyboard))


async def settings_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение формата и перерисовка меню формата."""
    query = update.callback_query
    if query is None:
        logger.warning("settings_format_callback: callback_query is None")
        return SettingsState.FORMAT_MENU.value

    await query.answer()
    data = query.data or ""
    uid = query.from_user.id

    if data.startswith(f"{CALLBACK_SET_FMT}|"):
        option = data.split("|", 1)[1]
        new_format = "ask" if option == "спрашивать" else option
        try:
            await set_user_settings(uid, preferred_format=new_format)
        except Exception:
            logger.exception("Ошибка сохранения формата для пользователя %s", uid)
        # показываем сразу выбранное значение
        await show_format_menu(uid, query, force_value=new_format)
        return SettingsState.FORMAT_MENU.value

    if data == CALLBACK_BACK_TO_MAIN:
        await show_main_settings_menu(uid, update)
        return SettingsState.MAIN_MENU.value

    return SettingsState.FORMAT_MENU.value


# ---------- Mode ----------

async def show_mode_menu(
    user_id: int,
    target: Union[CallbackQuery, Update],
    force_value: Optional[str] = None,
) -> None:
    """Меню выбора режима поиска."""
    try:
        user_settings = await get_user_settings(user_id)
    except Exception:
        logger.exception("Ошибка получения настроек пользователя %s", user_id)
        user_settings = {}

    selected_mode = force_value or user_settings.get("preferred_search_mode") or "general"
    mode_options = [("общий", "general"), ("только книги", "book"), ("только авторы", "author")]
    display_mode = next((text for text, mode in mode_options if mode == selected_mode), selected_mode)

    text_top = (
        "📌 <b>Настройки</b>\n"
        "━━━━━━━━━━━━━\n\n"
        "<b>Режим поиска.</b>\n\n"
        "<b>Текущий:</b>\n"
        f"<code>{html.escape(display_mode)}</code>\n\n"
        "━━━━━━━━━━━━━\n"
        "<b>Выберите, что меняем:</b>"
    )

    keyboard = []
    for display_text, option_value in mode_options:
        is_current = (option_value == selected_mode)
        caption = f"🔘 {display_text}" if is_current else display_text
        keyboard.append([InlineKeyboardButton(caption, callback_data=f"{CALLBACK_SET_MODE}|{option_value}")])
    keyboard.append([InlineKeyboardButton("Назад", callback_data=CALLBACK_BACK_TO_MAIN)])

    await send_or_edit_message(target, text_top, reply_markup=build_inline_keyboard(keyboard))


async def settings_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохранение режима и перерисовка меню режима."""
    query = update.callback_query
    if query is None:
        logger.warning("settings_mode_callback: callback_query is None")
        return SettingsState.MODE_MENU.value

    await query.answer()
    data = query.data or ""
    uid = query.from_user.id

    if data.startswith(f"{CALLBACK_SET_MODE}|"):
        option_value = data.split("|", 1)[1]
        try:
            await set_user_settings(uid, preferred_search_mode=option_value)
        except Exception:
            logger.exception("Ошибка сохранения режима поиска для пользователя %s", uid)
        await show_mode_menu(uid, query, force_value=option_value)
        return SettingsState.MODE_MENU.value

    if data == CALLBACK_BACK_TO_MAIN:
        await show_main_settings_menu(uid, update)
        return SettingsState.MAIN_MENU.value

    return SettingsState.MODE_MENU.value


# ---------- Main menu router ----------

async def settings_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Роутинг из главного меню."""
    query = update.callback_query
    if query is None:
        logger.warning("settings_main_menu_callback: callback_query is None")
        return SettingsState.MAIN_MENU.value

    await query.answer()
    data = query.data or ""
    uid = query.from_user.id

    if data == CALLBACK_SETTINGS_FORMAT:
        await show_format_menu(uid, query)
        return SettingsState.FORMAT_MENU.value
    if data == CALLBACK_SETTINGS_MODE:
        await show_mode_menu(uid, query)
        return SettingsState.MODE_MENU.value
    if data == CALLBACK_SETTINGS_BOOK_NAMING:
        await show_book_naming_menu(uid, query)
        return SettingsState.BOOK_NAMING_MENU.value

    return SettingsState.MAIN_MENU.value


# ---------- Conversation handler ----------

def get_settings_conversation_handler() -> ConversationHandler:
    """
    Конструктор ConversationHandler для /settings.
    """
    pattern_main   = r"^(" + re.escape(CALLBACK_SETTINGS_FORMAT) + "|" + re.escape(CALLBACK_SETTINGS_MODE) + "|" + re.escape(CALLBACK_SETTINGS_BOOK_NAMING) + r")$"
    pattern_fmt    = r"^(" + re.escape(CALLBACK_SET_FMT) + r"\|.*|" + re.escape(CALLBACK_BACK_TO_MAIN) + r")$"
    pattern_mode   = r"^(" + re.escape(CALLBACK_SET_MODE) + r"\|.*|" + re.escape(CALLBACK_BACK_TO_MAIN) + r")$"
    pattern_naming = r"^(" + re.escape(CALLBACK_SET_BOOK_NAMING) + r"\|.*|" + re.escape(CALLBACK_BACK_TO_MAIN) + r")$"

    return ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            SettingsState.MAIN_MENU.value: [
                CallbackQueryHandler(settings_main_menu_callback, pattern=pattern_main)
            ],
            SettingsState.FORMAT_MENU.value: [
                CallbackQueryHandler(settings_format_callback, pattern=pattern_fmt)
            ],
            SettingsState.MODE_MENU.value: [
                CallbackQueryHandler(settings_mode_callback, pattern=pattern_mode)
            ],
            SettingsState.BOOK_NAMING_MENU.value: [
                CallbackQueryHandler(settings_book_naming_callback, pattern=pattern_naming)
            ],
        },
        fallbacks=[],
        allow_reentry=True,
        per_message=False,
    )
