"""Общие фикстуры и герметичное окружение для тестов.

Переменные окружения задаются ДО импорта приложения: config.settings при
импорте валидирует ключи провайдеров и вызывает sys.exit(1) при их отсутствии.
load_dotenv() не перезаписывает уже заданные переменные (override=False),
поэтому тесты не зависят от реального .env и секретов.
"""

import os
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

# Фиксируем режим окружения для детерминированных настроек.
os.environ.setdefault("APP_ENV", "prod")

_DUMMY_ENV = {
    "YANDEX_FOLDER_ID": "dummy_folder",
    "YANDEX_API_KEY": "dummy_api_key",
    "YANDEX_MODEL": "dummy-model",
    "YANDEX_BASE_URL": "https://dummy.yandex.test/v1",
    "GIGACHAT_TOKEN": "dummy_token",
    "GIGACHAT_MODEL": "dummy-gigachat",
    "GIGACHAT_BASE_URL": "https://dummy.gigachat.test/api/v1",
    "GIGACHAT_OAUTH_URL": "https://dummy.gigachat.test/api/v2/oauth",
}
for key, value in _DUMMY_ENV.items():
    os.environ.setdefault(key, value)


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Тестовый HTTP-клиент приложения."""
    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def valid_request() -> dict:
    """Валидный payload для POST /api/generate-look."""
    return {
        "gender": "female",
        "age": 25,
        "style": "casual",
        "message": "Свидание в ресторане, хочу выглядеть стильно и элегантно",
    }
