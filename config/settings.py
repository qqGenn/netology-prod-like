"""Глобальная конфигурация приложения.

Загрузка и валидация:
1. .env файл (в .gitignore, пример заполнения смотреть в .env.example) -
   обязательные переменные окружения для LLM-провайдеров
2. APP_ENV (dev | prod) - выбирает набор параметров из config/:
   - config/base.py - базовые настройки, общие для всех режимов
   - config/dev.py / config/prod.py - переопределения под конкретный режим

Если провайдер включён в enabled_providers, но хотя бы одна его переменная
окружения не заполнена — приложение не стартует с ошибкой конфигурации.
"""

import os
import sys
from typing import Dict, List

from dotenv import load_dotenv

from config.dev import DEV_CONFIG
from config.prod import PROD_CONFIG
from core.log import logger

# Загружаем переменные окружения из .env файла (обязательно для работы)
load_dotenv()


class ConfigurationError(Exception):
    """Ошибка конфигурации приложения (config/*.py или .env)."""


# Режимы окружения приложения
SUPPORTED_ENVS = ("dev", "prod")

# Обязательные ключи конфигурации
REQUIRED_CONFIG_KEYS = (
    "max_retries",
    "wait_time_base",
    "timeout",
    "temperature",
    "max_tokens",
    "enabled_providers",
)

# Поддерживаемые LLM-провайдеры
SUPPORTED_PROVIDERS = ("yandex", "gigachat")

# Обязательные переменные окружения для каждого LLM-провайдера.
# Ключ — имя провайдера, значение — список переменных, которые должны быть заполнены.
PROVIDER_REQUIRED_ENV_VARS: Dict[str, List[str]] = {
    "yandex": [
        "YANDEX_FOLDER_ID",
        "YANDEX_API_KEY",
        "YANDEX_MODEL",
        "YANDEX_BASE_URL",
    ],
    "gigachat": [
        "GIGACHAT_TOKEN",
        "GIGACHAT_MODEL",
        "GIGACHAT_BASE_URL",
        "GIGACHAT_OAUTH_URL",
    ],
}

# Наборы конфигов для каждого режима APP_ENV
ENV_CONFIGS: Dict[str, dict] = {
    "dev": DEV_CONFIG,
    "prod": PROD_CONFIG,
}

# Режим окружения: APP_ENV=dev|prod (по умолчанию — prod)
APP_ENV = os.getenv("APP_ENV", "prod").strip().lower()


def load_config() -> dict:
    """Загружает конфигурацию под текущий APP_ENV.

    Собирает базовые настройки (config/base.py) и переопределения выбранного
    режима (config/dev.py или config/prod.py). При неизвестном APP_ENV —
    выбрасывает ConfigurationError.
    """
    if APP_ENV not in SUPPORTED_ENVS:
        raise ConfigurationError(
            f"APP_ENV='{APP_ENV}' не поддерживается. "
            f"Допустимые значения: {', '.join(SUPPORTED_ENVS)}"
        )

    config = ENV_CONFIGS[APP_ENV]

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ConfigurationError(
            f"В конфигурации для режима '{APP_ENV}' отсутствуют обязательные "
            f"ключи: {', '.join(missing)}"
        )

    logger.info(f"Конфигурация загружена. Режим APP_ENV={APP_ENV}: {config}")
    return config


def get_enabled_providers() -> list:
    """Возвращает список включённых провайдеров из конфигурации."""
    providers = app_config.get("enabled_providers")
    if not isinstance(providers, list) or not providers:
        raise ConfigurationError(
            "enabled_providers должен быть непустым списком (см. config/base.py)"
        )

    unknown = [p for p in providers if p not in SUPPORTED_PROVIDERS]
    if unknown:
        raise ConfigurationError(
            f"Неизвестные провайдеры в enabled_providers: {', '.join(unknown)}. "
            f"Поддерживаются: {', '.join(SUPPORTED_PROVIDERS)}"
        )
    return providers


def validate_environment() -> None:
    """Валидирует переменные окружения для включённых LLM-провайдеров.

    Для каждого провайдера из enabled_providers проверяется наличие всех его
    обязательных переменных окружения. При отсутствии хотя бы одной переменной
    приложение останавливается с ошибкой конфигурации.
    """
    enabled = get_enabled_providers()
    errors = []

    for provider, env_vars in PROVIDER_REQUIRED_ENV_VARS.items():
        if provider not in enabled:
            continue
        for var in env_vars:
            if not os.getenv(var):
                errors.append(
                    f"Переменная окружения {var} не заполнена (провайдер '{provider}' "
                    f"включён в enabled_providers). Проверьте .env файл"
                )

    if not any(p in enabled for p in SUPPORTED_PROVIDERS):
        errors.append(
            "Ни один провайдер не включён. Укажите 'yandex' и/или 'gigachat' "
            "в enabled_providers (см. config/base.py)"
        )

    if errors:
        for error in errors:
            logger.error(f"ОШИБКА: {error}")
        sys.exit(1)

    logger.info(f"Переменные окружения валидированы успешно. Провайдеры: {enabled}")


# Загружаем конфигурацию при импорте модуля - доступен по всему проекту
try:
    app_config = load_config()

    # Валидируем обязательные переменные окружения (остановка приложения при отсутствии)
    validate_environment()
except ConfigurationError as e:
    logger.error(f"ОШИБКА КОНФИГУРАЦИИ: {e}")
    sys.exit(1)
