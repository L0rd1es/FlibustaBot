# config.py

import os

# Админ Telegram ID — сюда бот будет присылать логи и статистику раз в сутки
ADMIN_ID = 689414006

# Список зеркал Флибусты
FLIBUSTA_MIRRORS = [
    "https://flibusta.is",
    "https://flibusta.site",
]

# Путь к файлу базы данных SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

# Лимит поиска (сколько результатов на страницу и т.д.) — если нужно
SEARCH_RESULTS_PER_PAGE = 5

# Логи, статистика
LOG_FILE = os.path.join(os.path.dirname(__file__), "bot.log")
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.log")

# --- Новые параметры для rate-limit ---
# Сколько запросов в секунду разрешено. Примеры:
#  - 2 => 2 запроса/сек
#  - 0.5 => 1 запрос каждые 2 секунды
RATE_LIMIT_RPS = 0.5

# --- Время отправки отчётов ---
# Строка "HH:MM", например "16:45".
SEND_REPORT_TIME = "16:45"