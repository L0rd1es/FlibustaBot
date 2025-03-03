# handlers.py

import logging
import re
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ChatAction

from service import (
    search_books_and_authors,
    get_book_details,
    download_book,
    get_author_books,
)
from db import get_user_settings, set_user_settings
from config import (
    SEARCH_RESULTS_PER_PAGE,
    STATS_FILE,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Одноразовый режим (эпhemeral) для /search, /book, /author
# ------------------------------------------------------------------
user_ephemeral_mode = {}

# ------------------------------------------------------------------
# Данные для пагинации
# user_search_data[user_id] = { "records": [...], "page": 1, "pages": N }
# ------------------------------------------------------------------
user_search_data = {}

# ------------------------------------------------------------------
# Храним message_id последнего бота
# user_last_bot_msg[user_id] = msg_id
# ------------------------------------------------------------------
user_last_bot_msg = {}

# ------------------------------------------------------------------
# Состояния ConversationHandler для /settings
# ------------------------------------------------------------------
SETTINGS_MENU, FORMAT_MENU, MODE_MENU = range(3)

# ------------------------------------------------------------------
# Утилита: удаляем сообщение юзера и последнее сообщение бота
# ------------------------------------------------------------------
async def cleanup_user_and_bot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить текущее (пользователя) и последнее (бота) сообщение."""
    user_id = update.effective_user.id

    # Удаляем пользовательское сообщение (если text_message)
    if getattr(update, "message", None):
        try:
            await update.message.delete()
        except:
            pass

    # Удаляем последнее бот-сообщение, если есть
    if user_id in user_last_bot_msg:
        mid = user_last_bot_msg[user_id]
        if mid:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=mid)
            except:
                pass
        user_last_bot_msg[user_id] = None

# ------------------------------------------------------------------
# Отправка chat_action "печатает..."
# ------------------------------------------------------------------
async def set_typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показываем 'Бот печатает...'."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)


# ==================================================================
# /search, /book, /author
# ==================================================================
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    user_ephemeral_mode[update.effective_user.id] = "general"
    await cleanup_user_and_bot_messages(update, context)
    msg = await update.message.reply_text("Следующий поиск будет «общим» (однократно).")
    user_last_bot_msg[update.effective_user.id] = msg.message_id

async def book_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    user_ephemeral_mode[update.effective_user.id] = "book"
    await cleanup_user_and_bot_messages(update, context)
    msg = await update.message.reply_text("Следующий поиск только по книгам (1 раз).")
    user_last_bot_msg[update.effective_user.id] = msg.message_id

async def author_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    user_ephemeral_mode[update.effective_user.id] = "author"
    await cleanup_user_and_bot_messages(update, context)
    msg = await update.message.reply_text("Следующий поиск только по авторам (1 раз).")
    user_last_bot_msg[update.effective_user.id] = msg.message_id

# ==================================================================
# /start /help
# ==================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    await cleanup_user_and_bot_messages(update, context)
    text = (
        "Привет! Я бот для поиска книг на Флибусте.\n\n"
        "Команды:\n"
        "/search - Общий поиск (1 раз)\n"
        "/book - Поиск книг (1 раз)\n"
        "/author - Поиск авторов (1 раз)\n"
        "/settings - Настройки формата/режима\n"
        "\nПросто введи запрос...\n"
        "Скачать: /download123\n"
        "Автор: /author123\n"
    )
    msg = await update.message.reply_text(text)
    user_last_bot_msg[update.effective_user.id] = msg.message_id

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    await cleanup_user_and_bot_messages(update, context)
    text = (
        "Помощь:\n"
        "/start - Начало\n"
        "/help - Это сообщение\n"
        "/settings - Настройки\n"
        "/search /book /author - одноразовые режимы\n\n"
        "Скачивание: /download<id>\n"
        "Автор: /author<id>\n"
    )
    msg = await update.message.reply_text(text)
    user_last_bot_msg[update.effective_user.id] = msg.message_id

# ==================================================================
# /settings (ConversationHandler)
# ==================================================================
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    await cleanup_user_and_bot_messages(update, context)
    await show_main_settings_menu(update.effective_user.id, update)
    return SETTINGS_MENU

async def show_main_settings_menu(user_id: int, update_or_query):
    st = get_user_settings(user_id)
    fm = st["preferred_format"] or ""
    md = st["preferred_search_mode"] or "general"

    text = (
        "НАСТРОЙКИ:\n\n"
        f"Формат: {fm if fm else 'спрашивать'}\n"
        f"Режим: {md if md!='general' else 'общий'}\n\n"
        "Выберите, что меняем:"
    )
    kb = [
        [InlineKeyboardButton("Формат", callback_data="settings_format")],
        [InlineKeyboardButton("Режим поиска", callback_data="settings_mode")],
    ]
    markup = InlineKeyboardMarkup(kb)

    if getattr(update_or_query, "callback_query", None):
        query = update_or_query.callback_query
        old_text = query.message.text or ""
        if old_text.strip()==text.strip():
            await query.answer("Без изменений")
            return
        await query.edit_message_text(text, reply_markup=markup)
    else:
        msg = await update_or_query.message.reply_text(text, reply_markup=markup)
        user_last_bot_msg[user_id] = msg.message_id

async def settings_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data=="settings_format":
        await show_format_menu(query.from_user.id, query)
        return FORMAT_MENU
    elif data=="settings_mode":
        await show_mode_menu(query.from_user.id, query)
        return MODE_MENU
    return SETTINGS_MENU

async def show_format_menu(user_id: int, query):
    st = get_user_settings(user_id)
    sel = st["preferred_format"]  # может быть "ask"

    # Если "ask", отображаем как "спрашивать", если нет — сам формат
    display_val = "спрашивать" if sel == "ask" else (sel or "спрашивать")

    text_top = f"Формат. Текущий: {display_val}\nВыберите формат:"
    arr = ["спрашивать","fb2","epub","mobi","pdf"]
    kb = []
    for opt in arr:
        # Специально храним "ask"
        val = "ask" if opt=="спрашивать" else opt
        is_selected = (val == sel)  # проверяем, равно ли "ask" или "fb2" и т.д.
        if is_selected:
            text_btn = f"🔘 {opt}"
        else:
            text_btn = opt
        kb.append([InlineKeyboardButton(text_btn, callback_data=f"set_fmt|{opt}")])

    kb.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
    ...
    await query.edit_message_text(text_top, reply_markup=InlineKeyboardMarkup(kb))

async def show_mode_menu(user_id: int, query):
    st = get_user_settings(user_id)
    sel = st["preferred_search_mode"] or "general"
    text_top = f"Режим. Текущий: {sel if sel!='general' else 'общий'}\nВыберите режим:"
    modes = [("общий","general"),("только книги","book"),("только авторы","author")]
    kb = []
    for (title, val) in modes:
        if val==sel:
            tbtn = f"🔘 {title}"
        else:
            tbtn = title
        kb.append([InlineKeyboardButton(tbtn, callback_data=f"set_mode|{val}")])

    kb.append([InlineKeyboardButton("Назад", callback_data="back_to_main")])
    old_text = query.message.text or ""
    if old_text.strip()==text_top.strip():
        await query.answer("Без изменений")
        return
    await query.edit_message_text(text_top, reply_markup=InlineKeyboardMarkup(kb))

async def settings_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("set_fmt|"):
        val = data.split("|")[1]  # "спрашивать"/"fb2"/"epub"...
        if val == "спрашивать":
            new_val = "ask"
        else:
            new_val = val  # "fb2", "epub", ...
        set_user_settings(user_id, preferred_format=new_val)
        await show_format_menu(user_id, query)
        return FORMAT_MENU
    elif data == "back_to_main":
        await show_main_settings_menu(user_id, update)
        return SETTINGS_MENU
    return FORMAT_MENU

async def settings_mode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    user_id = query.from_user.id
    if data.startswith("set_mode|"):
        val = data.split("|")[1]
        set_user_settings(user_id, preferred_search_mode=val)
        await show_mode_menu(user_id, query)
        return MODE_MENU
    elif data=="back_to_main":
        await show_main_settings_menu(user_id, update)
        return SETTINGS_MENU
    return MODE_MENU

def get_settings_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            SETTINGS_MENU: [
                CallbackQueryHandler(settings_main_menu_callback, pattern=r"^(settings_format|settings_mode)$")
            ],
            FORMAT_MENU: [
                CallbackQueryHandler(settings_format_callback, pattern=r"^(set_fmt\|.*|back_to_main)$")
            ],
            MODE_MENU: [
                CallbackQueryHandler(settings_mode_callback, pattern=r"^(set_mode\|.*|back_to_main)$")
            ],
        },
        fallbacks=[],
        allow_reentry=True,
        per_message=False
    )


# ------------------------------------------------------------------
# Пагинация
# ------------------------------------------------------------------
def build_page_text(user_id: int)->str:
    info = user_search_data[user_id]
    recs = info["records"]
    page = info["page"]
    pages = info["pages"]
    start_i = (page-1)*SEARCH_RESULTS_PER_PAGE
    end_i = start_i+SEARCH_RESULTS_PER_PAGE
    chunk = recs[start_i:end_i]

    lines = [f"Страница {page}/{pages}",""]
    lines.extend(chunk)
    return "\n".join(lines)

def build_pagination_kb(user_id: int):
    info = user_search_data[user_id]
    page = info["page"]
    pages = info["pages"]
    if pages<=1:
        return None
    btn_prev = InlineKeyboardButton("« Назад", callback_data="pagination|PREV") if page>1 else InlineKeyboardButton(" ", callback_data="no-op")
    btn_next = InlineKeyboardButton("Вперёд »", callback_data="pagination|NEXT") if page<pages else InlineKeyboardButton(" ", callback_data="no-op")
    row = [btn_prev, InlineKeyboardButton(f"{page}/{pages}", callback_data="no-op"), btn_next]
    return InlineKeyboardMarkup([row])

async def pagination_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    if user_id not in user_search_data:
        await query.edit_message_text("Данные для пагинации отсутствуют.")
        return
    info = user_search_data[user_id]
    if data=="pagination|NEXT" and info["page"]<info["pages"]:
        info["page"]+=1
    elif data=="pagination|PREV" and info["page"]>1:
        info["page"]-=1

    new_text = build_page_text(user_id)
    new_kb = build_pagination_kb(user_id)
    old_text = query.message.text or ""
    old_kb = query.message.reply_markup
    old_inline = old_kb.inline_keyboard if old_kb else []
    new_inline = new_kb.inline_keyboard if new_kb else []
    if new_text.strip()==old_text.strip() and old_inline==new_inline:
        return
    await query.edit_message_text(new_text, reply_markup=new_kb)

# ------------------------------------------------------------------
# /authorNNN => книги автора
# ------------------------------------------------------------------
async def author_books_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    await cleanup_user_and_bot_messages(update, context)

    text = update.message.text.strip()
    user_id = update.effective_user.id

    m = re.match(r"/author(\d+)$", text)
    if not m:
        msg = await update.message.reply_text("Некорректная команда /author12345")
        user_last_bot_msg[user_id] = msg.message_id
        return
    author_id = m.group(1)
    try:
        bks = get_author_books(author_id)
    except Exception as e:
        logger.error(e)
        msg = await update.message.reply_text("Не удалось получить книги автора.")
        user_last_bot_msg[user_id] = msg.message_id
        return

    if not bks:
        msg = await update.message.reply_text("У автора нет книг или автор не найден.")
        user_last_bot_msg[user_id] = msg.message_id
        return

    recs = []
    for b in bks:
        rec = f"{b['title']}\n{b['author']}\nСкачать: /download{b['id']}\n"
        recs.append(rec)

    total = len(recs)
    pages = (total + SEARCH_RESULTS_PER_PAGE -1)//SEARCH_RESULTS_PER_PAGE
    user_search_data[user_id] = {
        "records": recs,
        "page":1,
        "pages": pages,
    }
    txt = build_page_text(user_id)
    kb = build_pagination_kb(user_id)
    msg = await update.message.reply_text(txt, reply_markup=kb)
    user_last_bot_msg[user_id] = msg.message_id


# ------------------------------------------------------------------
# text_message_handler
# ------------------------------------------------------------------
async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    text = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # лог
    with open(STATS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{user_id}:{chat_id} -> {text}\n")

    # /download
    if text.startswith("/download"):
        await cleanup_user_and_bot_messages(update, context)
        book_id = text.removeprefix("/download").strip()
        if not book_id.isdigit():
            m = await update.message.reply_text("Некорректный ID.")
            user_last_bot_msg[user_id] = m.message_id
            return
        try:
            det = get_book_details(book_id)
        except Exception as e:
            logger.error(e)
            mm = await update.message.reply_text("Не удалось получить книгу.")
            user_last_bot_msg[user_id] = mm.message_id
            return

        # Если у пользователя есть preferred_format и он есть в det["formats"],
        # скачиваем сразу (без inline кнопок)
        st = get_user_settings(user_id)
        pfmt = st["preferred_format"]
        if pfmt and (pfmt in det["formats"]):
            # Сразу скачиваем
            try:
                file_data = download_book(book_id, pfmt)
                # Удаляем всё
                await cleanup_user_and_bot_messages(update, context)
                filename = f"{det['title'][:50]}_{book_id}.{pfmt}"
                capt = f"{det['title']}\nАвтор: {det['author']}"
                msg2 = await context.bot.send_document(
                    chat_id=chat_id,
                    document=file_data,
                    filename=filename,
                    caption=capt
                )
                user_last_bot_msg[user_id] = msg2.message_id
            except Exception as e:
                logger.error(e)
                # fallback: отправим inline кнопки
                mid = await send_book_details_message(update, context, det)
                user_last_bot_msg[user_id] = mid
        else:
            # Показываем "красивое" сообщение с кнопками
            mid = await send_book_details_message(update, context, det)
            user_last_bot_msg[user_id] = mid
        return

    # /author
    if text.startswith("/author") and text[7:].isdigit():
        await author_books_command(update, context)
        return

    # Иначе => поиск
    await cleanup_user_and_bot_messages(update, context)
    ephemeral = user_ephemeral_mode.get(user_id)
    if ephemeral:
        user_ephemeral_mode[user_id] = None
        mode = ephemeral
    else:
        st = get_user_settings(user_id)
        mode = st["preferred_search_mode"] or "general"

    try:
        data = search_books_and_authors(text, mode)
    except Exception as e:
        logger.error(e)
        mm = await update.message.reply_text("Ошибка при поиске.")
        user_last_bot_msg[user_id] = mm.message_id
        return

    bks = data["books_found"]
    auts = data["authors_found"]
    if not bks and not auts:
        mm = await update.message.reply_text("Ничего не найдено.")
        user_last_bot_msg[user_id] = mm.message_id
        return

    recs = []
    if auts:
        recs.append(f"Найдено авторов: {len(auts)}\n")
        for a in auts:
            rec = f"{a['name']} - {a['book_count']} книг\nКниги автора: /author{a['id']}\n"
            recs.append(rec)
    if bks:
        recs.append(f"Найдено книг: {len(bks)}\n")
        for b in bks:
            rec = f"{b['title']}\n{b['author']}\nСкачать: /download{b['id']}\n"
            recs.append(rec)

    total = len(recs)
    pages = (total+SEARCH_RESULTS_PER_PAGE-1)//SEARCH_RESULTS_PER_PAGE
    user_search_data[user_id] = {
        "records": recs,
        "page":1,
        "pages": pages,
    }
    txt = build_page_text(user_id)
    kb = build_pagination_kb(user_id)
    mm = await update.message.reply_text(txt, reply_markup=kb)
    user_last_bot_msg[user_id] = mm.message_id


# ------------------------------------------------------------------
# Красивое сообщение с кнопками форматов
# ------------------------------------------------------------------
async def send_book_details_message(update: Update, context: ContextTypes.DEFAULT_TYPE, details: dict):
    parts = []
    parts.append(details["title"] or "Без названия")
    if details["author"]:
        parts.append(f"Автор: {details['author']}")
    if details.get("year"):
        parts.append(f"Год: {details['year']}")
    if details.get("annotation"):
        parts.append(f"\n{details['annotation']}")

    cap = "\n".join(parts)

    fmts = details.get("formats", [])
    if fmts:
        row = []
        for f in fmts:
            row.append(InlineKeyboardButton(f, callback_data=f"choose_format|{details['id']}|{f}"))
        kb = InlineKeyboardMarkup([row])
    else:
        kb = None

    # обложка ?
    cover = None
    if details.get("cover_url"):
        try:
            r = requests.get(details["cover_url"], timeout=10)
            if r.status_code==200:
                cover = r.content
        except:
            pass

    if cover:
        msg = await update.message.reply_photo(
            photo=cover,
            caption=cap,
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        msg = await update.message.reply_text(
            text=cap,
            parse_mode="HTML",
            reply_markup=kb
        )
    return msg.message_id


# ------------------------------------------------------------------
# choose_format_callback => скачать => удалять => отправлять файл
# ------------------------------------------------------------------
async def choose_format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_typing_action(update, context)
    query = update.callback_query
    await query.answer()
    data = query.data
    _, book_id, fmt = data.split("|")

    try:
        file_data = download_book(book_id, fmt)
    except Exception as e:
        logger.error(e)
        await query.message.reply_text("Ошибка скачивания книги.")
        return

    # Получим детали
    try:
        d = get_book_details(book_id)
        t = d["title"][:50] if d["title"] else "book"
        a = d["author"] or ""
        cpt = f"{t}\nАвтор: {a}"
    except:
        t = f"book_{book_id}"
        cpt = t

    filename = f"{t}_{book_id}.{fmt}"

    # Удалим callback-сообщение + user
    await cleanup_user_and_bot_messages(update, context)

    chat_id = query.message.chat_id
    msg = await context.bot.send_document(
        chat_id=chat_id,
        document=file_data,
        filename=filename,
        caption=cpt
    )
    user_last_bot_msg[chat_id] = msg.message_id


async def no_op_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("")
