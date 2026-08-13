"""Переопределения настроек для режима разработки (APP_ENV=dev)."""

from config.base import BASE_CONFIG

DEV_CONFIG: dict = {
    **BASE_CONFIG,
    "max_retries": 2,
    "timeout": 45,
}
