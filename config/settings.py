"""Глобальная конфигурация приложения.

Загрузка и валидация:
1. .env файл (в .gitignore, пример заполнения смотреть в .env.example) - обязательные переменные окружения для LLM-провайдеров
2. config/main.json (под git) - параметры конфигурации приложения

Если провайдер включён в enabled_providers, но хотя бы одна его переменная
окружения не заполнена — приложение не стартует с ошибкой конфигурации.
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from core.log import logger

# Загружаем переменные окружения из .env файла (обязательно для работы)
load_dotenv()


class ConfigurationError(Exception):
    """Ошибка конфигурации приложения (config/main.json или .env)."""


# Обязательные ключи config/main.json
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


def load_json_config() -> dict:
    """Загружает и валидирует JSON-конфигурацию из config/main.json.

    При отсутствии файла, некорректном JSON или пропущенных обязательных
    ключах — выбрасывает ConfigurationError.
    """
    project_dir = Path(__file__).parents[1]
    config_path = os.path.join(project_dir, "config", "main.json")
    if not os.path.exists(config_path):
        raise ConfigurationError(f"Файл config/main.json не найден: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        raise ConfigurationError(f"Ошибка при загрузке config/main.json: {e}") from e

    if not isinstance(config, dict):
        raise ConfigurationError("config/main.json должен содержать JSON-объект")

    missing = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing:
        raise ConfigurationError(
            f"В config/main.json отсутствуют обязательные ключи: {', '.join(missing)}"
        )

    logger.info(f"JSON-конфигурация загружена из main.json: {config}")
    return config


def get_enabled_providers() -> list:
    """Возвращает список включённых провайдеров из config/main.json."""
    providers = json_config.get("enabled_providers")
    if not isinstance(providers, list) or not providers:
        raise ConfigurationError(
            "enabled_providers в config/main.json должен быть непустым списком"
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
            "в enabled_providers в config/main.json"
        )

    if errors:
        for error in errors:
            logger.error(f"ОШИБКА: {error}")
        sys.exit(1)

    logger.info(f"Переменные окружения валидированы успешно. Провайдеры: {enabled}")


# Загружаем JSON-конфигурацию при импорте модуля - доступен по всему проекту
try:
    json_config = load_json_config()

    # Валидируем обязательные переменные окружения (остановка приложения при отсутствии)
    validate_environment()
except ConfigurationError as e:
    logger.error(f"ОШИБКА КОНФИГУРАЦИИ: {e}")
    sys.exit(1)
