"""Базовые настройки приложения, общие для всех режимов (APP_ENV).

Здесь хранятся параметры, одинаковые для dev и prod.
Переопределения под конкретный режим — в config/dev.py и config/prod.py.
"""

# Параметры, общие для всех сред
BASE_CONFIG: dict = {
    "wait_time_base": 2,
    "temperature": 0.33,
    "max_tokens": 2000,
    "enabled_providers": ["yandex", "gigachat"],
}
