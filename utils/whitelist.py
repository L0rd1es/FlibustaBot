# utils/whitelist.py

import json
import os
import logging
import re
from typing import List, Optional
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# Путь к файлу whitelist (список строк вида "@username")
WHITELIST_FILE = os.path.join(os.path.dirname(__file__), "whitelist.json")

# Кэш: чтобы не читать файл на каждый чих
_cached_mtime: Optional[float] = None
_cached_list: Optional[List[str]] = None


def _read_file_safely(path: str) -> List[str]:
    """Читает JSON-список строк из файла. Возвращает [] при любой ошибке."""
    if not os.path.exists(path):
        logger.info("Файл %s не найден, возвращаем пустой список.", path)
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error("Файл %s не содержит список, возвращаем пустой список.", path)
            return []
        # нормализуем: только строки, без пробелов, в нижнем регистре
        out = []
        for entry in data:
            if isinstance(entry, str):
                entry = entry.strip()
                if entry:
                    out.append(entry.lower())
        return out
    except Exception as e:
        logger.exception("Ошибка чтения %s: %s", path, e)
        return []


def load_whitelist() -> List[str]:
    """
    Загружает список разрешённых юзернеймов из файла с кэшем по mtime.
    Все юзернеймы в виде '@username' и в нижнем регистре.
    """
    global _cached_mtime, _cached_list  # <-- объявляем до присваиваний

    try:
        mtime = os.path.getmtime(WHITELIST_FILE) if os.path.exists(WHITELIST_FILE) else None
    except Exception:
        mtime = None

    # если кэш свежий — используем его
    if _cached_list is not None and _cached_mtime == mtime:
        return _cached_list

    # перечитываем файл
    wl = _read_file_safely(WHITELIST_FILE)
    _cached_list = wl
    _cached_mtime = mtime
    return wl


def _write_whitelist(data: List[str]) -> None:
    """Атомарная запись файла, с обновлением кэша."""
    tmp_path = WHITELIST_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, WHITELIST_FILE)
        # обновляем кэш
        global _cached_mtime, _cached_list
        _cached_list = data[:]
        _cached_mtime = os.path.getmtime(WHITELIST_FILE)
        logger.info("Whitelist успешно сохранён.")
    except Exception as e:
        # убираем временный файл, если что-то пошло не так
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        logger.exception("Ошибка сохранения вайтлиста: %s", e)


def save_whitelist(whitelist: List[str]) -> None:
    """Публичная обёртка — сохраняет список."""
    _write_whitelist(whitelist)


def is_whitelisted(user) -> bool:
    """
    Проверяет, находится ли пользователь в вайтлисте.
    Администратор (ADMIN_ID) всегда имеет доступ.
    Проверка ведётся по юзернейму (с '@').
    """
    if user.id == ADMIN_ID:
        return True
    if not getattr(user, "username", None):
        logger.debug("Пользователь %s без username — доступ запрещён.", user.id)
        return False

    current_username = "@" + user.username.lower()
    return current_username in load_whitelist()


def add_user_to_whitelist(username: str) -> bool:
    """
    Добавляет юзернейм (в любом регистре, с/без '@') в вайтлист.
    Возвращает True, если добавили новый.
    """
    uname = username.strip().lower()
    if not uname:
        return False
    if not uname.startswith("@"):
        uname = "@" + uname

    wl = load_whitelist()
    if uname in wl:
        logger.info("Юзернейм %s уже в вайтлисте.", uname)
        return False

    wl.append(uname)
    save_whitelist(wl)
    logger.info("Юзернейм %s добавлен в вайтлист.", uname)
    return True


def remove_user_from_whitelist(username: str) -> bool:
    """
    Удаляет юзернейм (с/без '@', любой регистр) из вайтлиста.
    Возвращает True, если запись была удалена.
    """
    uname = username.strip().lower()
    if not uname:
        return False
    if not uname.startswith("@"):
        uname = "@" + uname

    wl = load_whitelist()
    if uname not in wl:
        logger.info("Юзернейм %s не найден в вайтлисте.", uname)
        return False

    wl.remove(uname)
    save_whitelist(wl)
    logger.info("Юзернейм %s удалён из вайтлиста.", uname)
    return True


def whitelist_required(func):
    """
    Декоратор для проверки вайтлиста.
    Если пользователь не в вайтлисте — отправляет сообщение и не вызывает обработчик.
    """
    async def wrapper(update, context, *args, **kwargs):
        try:
            user = update.effective_user
            if not is_whitelisted(user):
                logger.info("Доступ запрещён для пользователя %s.", f"@{user.username}" if user.username else user.id)
                if update.message:
                    await update.message.reply_text("У вас нет доступа к боту. Обратитесь к администратору: @Lordies")
                return
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.exception("Ошибка в whitelist_required: %s", e)
    return wrapper


async def process_whitelist(update, context):
    """
    Тогглит пользователя в вайтлисте.
    Админ отправляет сообщение с @username — добавляем/удаляем.
    """
    try:
        if update.effective_user.id != ADMIN_ID:
            return

        text = (update.message.text or "").strip()
        m = re.fullmatch(r"@(\w+)", text)
        if not m:
            await update.message.reply_text("Неверный формат. Отправьте юзернейм: @username")
            return

        username = m.group(0)  # c '@'
        try:
            target = await context.bot.get_chat(username)
            if getattr(target, "username", None):
                username = "@" + target.username
        except Exception as e:
            logger.warning("get_chat(%s) не удался: %s — продолжаем с переданным текстом.", username, e)

        uname_l = username.lower()
        wl = load_whitelist()
        if uname_l in wl:
            ok = remove_user_from_whitelist(uname_l)
            await update.message.reply_text(f"Юзернейм {username} удалён из вайтлиста." if ok else "Ошибка при удалении.")
        else:
            ok = add_user_to_whitelist(uname_l)
            await update.message.reply_text(f"Юзернейм {username} добавлен в вайтлист." if ok else "Ошибка при добавлении.")
    except Exception as e:
        logger.exception("Ошибка в process_whitelist: %s", e)
        try:
            await update.message.reply_text("Произошла ошибка при обработке сообщения.")
        except Exception:
            pass
