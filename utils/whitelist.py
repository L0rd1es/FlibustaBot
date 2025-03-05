import json
import os
import logging
import re
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# Путь к файлу, где хранится вайтлист (список юзернеймов, например, ["@juligni", "@username2"])
WHITELIST_FILE = os.path.join(os.path.dirname(__file__), 'whitelist.json')


def load_whitelist() -> list:
    """
    Загружает список разрешённых юзернеймов из файла.
    Если файла нет или произошла ошибка, возвращается пустой список.
    Все юзернеймы приводятся к нижнему регистру.
    """
    if not os.path.exists(WHITELIST_FILE):
        logger.info("Файл whitelist.json не найден, возвращаем пустой список.")
        return []
    try:
        with open(WHITELIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error("Файл whitelist.json не содержит список, возвращаем пустой список.")
            return []
        return [entry.lower() for entry in data]
    except Exception as e:
        logger.exception(f"Ошибка загрузки вайтлиста: {e}")
        return []


def save_whitelist(whitelist: list) -> None:
    """
    Сохраняет список разрешённых юзернеймов в файл.
    """
    try:
        with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(whitelist, f, ensure_ascii=False, indent=2)
        logger.info("Whitelist успешно сохранён.")
    except Exception as e:
        logger.exception(f"Ошибка сохранения вайтлиста: {e}")


def is_whitelisted(user) -> bool:
    """
    Проверяет, находится ли пользователь в вайтлисте.
    Администратор (ADMIN_ID) всегда имеет доступ.
    Проверка ведётся по юзернейму (с добавлением символа @).
    """
    if user.id == ADMIN_ID:
        return True
    if not user.username:
        logger.debug(f"Пользователь {user.id} не имеет юзернейма, доступ запрещён.")
        return False
    whitelist = load_whitelist()
    current_username = "@" + user.username.lower()
    in_list = current_username in whitelist
    logger.debug(f"Проверка вайтлиста для {current_username}: {'есть в списке' if in_list else 'нет в списке'}.")
    return in_list


def add_user_to_whitelist(username: str) -> bool:
    """
    Добавляет юзернейм в вайтлист.
    Возвращает True, если юзернейм был успешно добавлен.
    """
    try:
        whitelist = load_whitelist()
        uname = username.lower()
        if uname not in whitelist:
            whitelist.append(uname)
            save_whitelist(whitelist)
            logger.info(f"Юзернейм {uname} добавлен в вайтлист.")
            return True
        else:
            logger.info(f"Юзернейм {uname} уже находится в вайтлисте.")
            return False
    except Exception as e:
        logger.exception(f"Ошибка при добавлении юзернейма {username} в вайтлист: {e}")
        return False


def remove_user_from_whitelist(username: str) -> bool:
    """
    Удаляет юзернейм из вайтлиста.
    Возвращает True, если юзернейм был найден и удалён.
    """
    try:
        whitelist = load_whitelist()
        uname = username.lower()
        if uname in whitelist:
            whitelist.remove(uname)
            save_whitelist(whitelist)
            logger.info(f"Юзернейм {uname} удалён из вайтлиста.")
            return True
        else:
            logger.info(f"Юзернейм {uname} не найден в вайтлисте.")
            return False
    except Exception as e:
        logger.exception(f"Ошибка при удалении юзернейма {username} из вайтлиста: {e}")
        return False


def whitelist_required(func):
    """
    Декоратор для проверки вайтлиста.
    Если пользователь не в вайтлисте, отправляет сообщение об отсутствии доступа и не вызывает функцию-обработчик.
    Проверка ведётся по юзернейму.
    """
    async def wrapper(update, context, *args, **kwargs):
        try:
            user = update.effective_user
            if not is_whitelisted(user):
                logger.info(f"Доступ запрещён для пользователя @{user.username if user.username else user.id}.")
                if update.message:
                    await update.message.reply_text("У вас нет доступа к боту. Обратитесь к администратору: @Lordies")
                return
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Ошибка в декораторе whitelist_required: {e}")
    return wrapper


async def process_whitelist(update, context):
    """
    Обрабатывает сообщение от администратора для добавления/удаления юзернейма в/из вайтлиста.
    Ожидается, что сообщение содержит юзернейм в формате @username.
    Если юзернейм уже есть в вайтлисте – удаляет его, иначе – добавляет.
    """
    try:
        if update.effective_user.id != ADMIN_ID:
            logger.info("Сообщение не от администратора, обработка пропущена.")
            return

        if not update.message.text:
            logger.warning("Сообщение не содержит текст.")
            return

        text = update.message.text.strip()
        match = re.fullmatch(r'@(\w+)', text)
        if not match:
            logger.warning("Текстовое сообщение не является корректным юзернеймом.")
            await update.message.reply_text("Неверный формат. Отправьте юзернейм в формате: @username")
            return

        username = match.group(0)  # уже с символом '@'
        # Попытка получить данные по юзернейму; если не удаётся, работаем с самим текстом
        try:
            target_chat = await context.bot.get_chat(username)
            username = ("@" + target_chat.username) if target_chat.username else username
        except Exception as e:
            logger.warning(f"Не удалось получить информацию по юзернейму {username}: {e}")
            # Продолжаем работать с полученным юзернеймом

        if username.lower() in load_whitelist():
            removed = remove_user_from_whitelist(username)
            if removed:
                await update.message.reply_text(f"Юзернейм {username} удалён из вайтлиста.")
            else:
                await update.message.reply_text("Ошибка при удалении юзернейма из вайтлиста.")
        else:
            added = add_user_to_whitelist(username)
            if added:
                await update.message.reply_text(f"Юзернейм {username} добавлен в вайтлист.")
            else:
                await update.message.reply_text("Ошибка при добавлении юзернейма в вайтлист.")
    except Exception as e:
        logger.exception(f"Ошибка в process_whitelist: {e}")
        try:
            await update.message.reply_text("Произошла ошибка при обработке сообщения.")
        except Exception as inner_e:
            logger.exception(f"Ошибка при отправке сообщения об ошибке: {inner_e}")
