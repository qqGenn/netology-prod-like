"""Переопределения настроек для продакшна (APP_ENV=prod).

Используются текущие настройки приложения.
"""

from config.base import BASE_CONFIG

PROD_CONFIG: dict = {
    **BASE_CONFIG,
    "max_retries": 3,
    "timeout": 40,
}
