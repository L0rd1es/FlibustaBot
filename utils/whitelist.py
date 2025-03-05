import json
import os
import logging
import re
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# Путь к файлу, где хранится вайтлист (список user_id)
WHITELIST_FILE = os.path.join(os.path.dirname(__file__), 'whitelist.json')


def load_whitelist() -> list:
    """
    Загружает список разрешённых пользователей из файла.
    Если файла нет или произошла ошибка, возвращается пустой список.
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
        return data
    except Exception as e:
        logger.exception(f"Ошибка загрузки вайтлиста: {e}")
        return []


def save_whitelist(whitelist: list) -> None:
    """
    Сохраняет список разрешённых пользователей в файл.
    """
    try:
        with open(WHITELIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(whitelist, f, ensure_ascii=False, indent=2)
        logger.info("Whitelist успешно сохранён.")
    except Exception as e:
        logger.exception(f"Ошибка сохранения вайтлиста: {e}")


def is_whitelisted(user_id: int) -> bool:
    """
    Проверяет, находится ли пользователь в вайтлисте.
    Администратор (ADMIN_ID) всегда имеет доступ.
    """
    if user_id == ADMIN_ID:
        return True
    whitelist = load_whitelist()
    in_list = user_id in whitelist
    logger.debug(f"Проверка вайтлиста для пользователя {user_id}: {'есть в списке' if in_list else 'нет в списке'}.")
    return in_list


def add_user_to_whitelist(user_id: int) -> bool:
    """
    Добавляет пользователя в вайтлист.
    Возвращает True, если пользователь был успешно добавлен.
    """
    try:
        whitelist = load_whitelist()
        if user_id not in whitelist:
            whitelist.append(user_id)
            save_whitelist(whitelist)
            logger.info(f"Пользователь {user_id} добавлен в вайтлист.")
            return True
        else:
            logger.info(f"Пользователь {user_id} уже находится в вайтлисте.")
            return False
    except Exception as e:
        logger.exception(f"Ошибка при добавлении пользователя {user_id} в вайтлист: {e}")
        return False


def remove_user_from_whitelist(user_id: int) -> bool:
    """
    Удаляет пользователя из вайтлиста.
    Возвращает True, если пользователь был найден и удалён.
    """
    try:
        whitelist = load_whitelist()
        if user_id in whitelist:
            whitelist.remove(user_id)
            save_whitelist(whitelist)
            logger.info(f"Пользователь {user_id} удалён из вайтлиста.")
            return True
        else:
            logger.info(f"Пользователь {user_id} не найден в вайтлисте.")
            return False
    except Exception as e:
        logger.exception(f"Ошибка при удалении пользователя {user_id} из вайтлиста: {e}")
        return False


def whitelist_required(func):
    """
    Декоратор для проверки вайтлиста.
    Если пользователь не в вайтлисте, отправляет сообщение об отсутствии доступа и не вызывает функцию-обработчик.
    """
    async def wrapper(update, context, *args, **kwargs):
        try:
            user_id = update.effective_user.id
            if not is_whitelisted(user_id):
                logger.info(f"Доступ запрещён для пользователя {user_id}.")
                if update.message:
                    await update.message.reply_text("У вас нет доступа к боту. Обратитесь к администратору.")
                return
            return await func(update, context, *args, **kwargs)
        except Exception as e:
            logger.exception(f"Ошибка в декораторе whitelist_required: {e}")
    return wrapper


async def process_whitelist(update, context):
    """
    Обрабатывает сообщение от администратора для добавления/удаления пользователя из вайтлиста.
    Ожидается, что сообщение содержит юзернейм в формате @username.
    Если юзернейм уже есть в вайтлисте – удаляет пользователя, иначе – добавляет.
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

        username = match.group(0)  # включает символ @
        try:
            target_chat = await context.bot.get_chat(username)
        except Exception as e:
            logger.error(f"Не удалось получить данные по юзернейму {username}: {e}")
            await update.message.reply_text(f"Не удалось получить информацию по юзернейму {username}.")
            return

        target_id = target_chat.id
        display_name = getattr(target_chat, 'first_name', None) or getattr(target_chat, 'title', None) or username

        if is_whitelisted(target_id):
            removed = remove_user_from_whitelist(target_id)
            if removed:
                await update.message.reply_text(
                    f"Пользователь {display_name} (ID: {target_id}) удалён из вайтлиста."
                )
            else:
                await update.message.reply_text("Ошибка при удалении пользователя из вайтлиста.")
        else:
            added = add_user_to_whitelist(target_id)
            if added:
                await update.message.reply_text(
                    f"Пользователь {display_name} (ID: {target_id}) добавлен в вайтлист."
                )
            else:
                await update.message.reply_text("Ошибка при добавлении пользователя в вайтлист.")
    except Exception as e:
        logger.exception(f"Ошибка в process_whitelist: {e}")
        try:
            await update.message.reply_text("Произошла ошибка при обработке сообщения.")
        except Exception as inner_e:
            logger.exception(f"Ошибка при отправке сообщения об ошибке: {inner_e}")
