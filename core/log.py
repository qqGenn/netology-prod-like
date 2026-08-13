import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Создаем папку для логов, если её нет
os.makedirs("logs", exist_ok=True)


class JSONFormatter(logging.Formatter):
    """Форматтер логов в формате JSON."""

    def format(self, record):
        # Получаем только имя файла без пути
        filename = Path(record.pathname).name
        log_entry = {
            "source": f"{filename}@{record.funcName}",
            "msg": record.getMessage(),
            "level": record.levelname,
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
        }
        return json.dumps(log_entry, ensure_ascii=False)


# Настройка консольного хендлера - выводит INFO и выше
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(JSONFormatter())

# Настройка файлового хендлера - выводит DEBUG и выше
file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(JSONFormatter())

# Базовый уровень - DEBUG, чтобы файловый хендлер мог логировать debug
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[console_handler, file_handler],
)

logger = logging.getLogger(__name__)
