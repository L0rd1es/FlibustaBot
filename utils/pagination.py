import logging
from typing import cast
from math import ceil
from typing import Optional, TypedDict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import SEARCH_RESULTS_PER_PAGE
from utils.state import get_user_search_data, update_user_search_page
from utils.utils import send_or_edit_message

logger = logging.getLogger(__name__)

# Константы для callback-данных
CB_PREFIX = "pagination"
CB_NEXT = f"{CB_PREFIX}|NEXT"
CB_PREV = f"{CB_PREFIX}|PREV"
CB_NOOP = "no-op"


class SearchState(TypedDict):
    records: list[str]
    page: int
    pages: int


def _safe_per_page() -> int:
    """Гарантируем валидное значение размера страницы (минимум 1)."""
    try:
        n = int(SEARCH_RESULTS_PER_PAGE)
    except Exception:
        n = 10
    return max(1, n)


def _compute_total_pages(records_count: int, per_page: int) -> int:
    return max(1, ceil(records_count / per_page)) if records_count > 0 else 1


def build_page_text(user_id: int) -> str:
    """
    Формирует текст для текущей страницы с результатами поиска.
    """
    info = cast(Optional[SearchState], get_user_search_data(user_id))
    if not info:
        return "Данные поиска отсутствуют."

    records = info.get("records", []) or []
    current_page = int(info.get("page", 1) or 1)

    per_page = _safe_per_page()
    total_pages_dynamic = _compute_total_pages(len(records), per_page)

    # Если сохранённый total_pages устарел — используем динамический
    total_pages = max(int(info.get("pages", 1) or 1), 1)
    if total_pages != total_pages_dynamic:
        total_pages = total_pages_dynamic

    # Зажимаем текущую страницу в допустимые границы
    if current_page > total_pages:
        current_page = total_pages
    if current_page < 1:
        current_page = 1

    if not records:
        return "Ничего не найдено."

    start_index = (current_page - 1) * per_page
    end_index = start_index + per_page
    chunk = records[start_index:end_index]

    # Если после пересчёта вдруг пусто (например, список сократился) — откат на последнюю страницу
    if not chunk and total_pages > 1:
        start_index = (total_pages - 1) * per_page
        end_index = start_index + per_page
        chunk = records[start_index:end_index]
        current_page = total_pages

    lines = [f"Страница {current_page}/{total_pages}", ""]
    lines.extend(chunk)
    return "\n".join(lines)


def build_pagination_kb(user_id: int) -> Optional[InlineKeyboardMarkup]:
    """
    Создаёт кнопки навигации для пагинации.
    """
    info = cast(Optional[SearchState], get_user_search_data(user_id))
    if not info:
        return None

    records = info.get("records", []) or []
    per_page = _safe_per_page()
    total_pages_dynamic = _compute_total_pages(len(records), per_page)

    current_page = int(info.get("page", 1) or 1)
    total_pages_saved = max(int(info.get("pages", 1) or 1), 1)
    total_pages = max(total_pages_dynamic, total_pages_saved)  # подстраховка

    if total_pages <= 1:
        return None

    # Зажимаем текущую страницу
    if current_page > total_pages:
        current_page = total_pages
    if current_page < 1:
        current_page = 1

    # Кнопки
    btn_prev = InlineKeyboardButton("« Назад", callback_data=CB_PREV) if current_page > 1 else InlineKeyboardButton(" ", callback_data=CB_NOOP)
    btn_next = InlineKeyboardButton("Вперёд »", callback_data=CB_NEXT) if current_page < total_pages else InlineKeyboardButton(" ", callback_data=CB_NOOP)

    row = [
        btn_prev,
        InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data=CB_NOOP),
        btn_next,
    ]
    return InlineKeyboardMarkup([row])


async def pagination_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатия кнопок пагинации и обновляет сообщение с новыми результатами поиска.
    """
    query = update.callback_query
    if not query:
        logger.error("Callback query отсутствует в update.")
        return

    try:
        await query.answer(cache_time=0, show_alert=False)
    except Exception:
        # не критично, продолжаем
        pass

    data = query.data or ""
    if not data.startswith(f"{CB_PREFIX}|"):
        logger.warning("Неизвестное действие пагинации: %r", data)
        return

    user_id = query.from_user.id if query.from_user else None
    if not user_id:
        logger.warning("Нет from_user в callback_query.")
        return

    search_data = get_user_search_data(user_id)
    if not search_data:
        await query.edit_message_text("Данные для пагинации отсутствуют.")
        return

    if data == CB_NEXT:
        update_user_search_page(user_id, "NEXT")
        logger.info("Пользователь %s переключил на следующую страницу.", user_id)
    elif data == CB_PREV:
        update_user_search_page(user_id, "PREV")
        logger.info("Пользователь %s переключил на предыдущую страницу.", user_id)
    else:
        logger.warning("Неизвестное действие пагинации: %r", data)

    new_text = build_page_text(user_id)
    new_kb = build_pagination_kb(user_id)
    await send_or_edit_message(update, new_text, reply_markup=new_kb)
