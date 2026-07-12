# config.py

import os

# Админ Telegram ID — сюда бот будет присылать логи и статистику раз в сутки
ADMIN_ID = 689414006

# Список зеркал Флибусты (порядок = приоритет; следующие — fallback)
FLIBUSTA_MIRRORS = [
    "https://flibusta.is",
    "http://flibusta.site",  # HTTPS редиректит на HTTP и часто зависает
]

# Persistent data directory (Docker mounts ./data at /app/data).
_PROJECT_ROOT = os.path.dirname(__file__)
DATA_DIR = os.environ.get("DATA_DIR", _PROJECT_ROOT)
os.makedirs(DATA_DIR, exist_ok=True)

# Путь к файлу базы данных SQLite
DB_PATH = os.path.join(DATA_DIR, "users.db")

# Лимит поиска (сколько результатов на страницу и т.д.) — если нужно
SEARCH_RESULTS_PER_PAGE = 5

# Максимальная длина названия книги в имени файла (без учета длины имени автора и ID)
MAX_TITLE_LENGTH = 30 

# Логи, статистика
LOG_FILE = os.path.join(DATA_DIR, "bot.log")
STATS_FILE = os.path.join(DATA_DIR, "stats.log")

# --- Новые параметры для rate-limit ---
# Сколько запросов в секунду разрешено. Примеры:
#  - 2 => 2 запроса/сек
#  - 0.5 => 1 запрос каждые 2 секунды
RATE_LIMIT_RPS = 0.5

# Таймаут HTTP-запросов к зеркалам Флибусты (сек). Сайт иногда отвечает >10 с.
FETCH_TIMEOUT_SECONDS = 25

# --- Время отправки отчётов ---
# Строка "HH:MM", например "16:45".
SEND_REPORT_TIME = "16:45"

# Очистка из оперативной памяти данных старше указанного ниже числа (в секундах)
DATA_EXPIRATION_TIME = 600