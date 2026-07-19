"""Настройки Mini App. Всё, что берётся из окружения, — только здесь."""
import os
from pathlib import Path

# Токен нужен не для походов в Telegram (туда этот сервис не ходит вообще),
# а чтобы проверять подпись initData. См. auth.py.
BOT_TOKEN = os.environ["MINIAPP_BOT_TOKEN"]

# Сколько живёт подписанный initData. Сутки — компромисс: тренировка длится час-два,
# но человек может открыть приложение, не перезапуская клиент Telegram.
MAX_AUTH_AGE = int(os.getenv("MINIAPP_MAX_AUTH_AGE", "86400"))

STATIC_DIR = Path(__file__).parent / "static"

WEEK_DAYS_RU = [
    "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
]

# Ограничения ввода — дублируют то, что валидируют схемы, но нужны и в других местах.
MAX_PROGRAM_NAME = 50
MAX_USER_NAME = 20
