"""Тесты fallback и ретраев ImageMakerService.

Вместо реального LLM-клиента используется FakeLLM с управляемым поведением
провайдеров. Сетевая ошибка (LLM_CLIENT_REQUEST_FAILED) должна ретраиться и
приводить к fallback на следующий провайдер, ошибка валидации — нет.
"""

from typing import Any, Awaitable, Callable, Dict

import pytest

from config.settings import app_config
from llm.errors import LLM_CLIENT_REQUEST_FAILED, LLM_CLIENT_VALIDATION_ERROR
from models.schemas import Gender, LookCreate, Style
from services.image_maker_service import ImageMakerService

Handler = Callable[..., Awaitable[dict]]

VALID_LOOK = {
    "look_variants": [
        {
            "title": "Элегантный образ",
            "target": "Цель образа",
            "description": "Подробное описание образа",
        }
    ],
    "recommendation": "Рекомендация по итоговому образу",
}


class FakeLLM:
    """Фейковый LLM-клиент: цепочка провайдеров и управляемые ответы."""

    def __init__(self, chain: list, handler: Handler) -> None:
        self._chain = chain
        self._handler = handler
        self.calls: Dict[str, int] = {}

    def get_provider_chain(self) -> list:
        return list(self._chain)

    def get_provider_model(self, provider: str) -> str:
        return f"model-{provider}"

    async def generate_looks_from_provider(self, provider: str, **kwargs: Any) -> dict:
        self.calls[provider] = self.calls.get(provider, 0) + 1
        return await self._handler(provider, **kwargs)


@pytest.fixture
def service() -> Any:
    """Экземпляр ImageMakerService без инициализации реальных зависимостей."""
    return ImageMakerService.__new__(ImageMakerService)


def make_request() -> LookCreate:
    return LookCreate(
        gender=Gender.FEMALE, age=25, style=Style.CASUAL, message="Свидание в ресторане"
    )


@pytest.mark.asyncio
async def test_call_llm_falls_back_to_secondary_provider(service: Any) -> None:
    """Primary недоступен (сетевая ошибка) → результат берётся от secondary."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        if provider == "yandex":
            raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: сеть недоступна")
        return VALID_LOOK

    service.llm = FakeLLM(["yandex", "gigachat"], handler)

    result = await service._call_llm(make_request())

    assert result == VALID_LOOK
    assert service.llm.calls["gigachat"] == 1
    assert service.llm.calls["yandex"] == app_config["max_retries"]


@pytest.mark.asyncio
async def test_call_llm_retries_retryable_error_then_succeeds(service: Any) -> None:
    """Первая попытка падает с сетевой ошибкой → ретрай, затем успех."""
    attempts = {"n": 0}

    async def handler(provider: str, **kwargs: Any) -> dict:
        if provider != "yandex":
            return VALID_LOOK
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: таймаут")
        return VALID_LOOK

    service.llm = FakeLLM(["yandex", "gigachat"], handler)

    result = await service._call_llm(make_request())

    assert result == VALID_LOOK
    assert service.llm.calls["yandex"] == 2
    assert service.llm.calls.get("gigachat", 0) == 0


@pytest.mark.asyncio
async def test_call_llm_non_retryable_error_is_not_retried(service: Any) -> None:
    """Ошибка валидации ответа не ретраится, происходит fallback на secondary."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        if provider == "yandex":
            raise Exception(f"{LLM_CLIENT_VALIDATION_ERROR}: плохой ответ")
        return VALID_LOOK

    service.llm = FakeLLM(["yandex", "gigachat"], handler)

    result = await service._call_llm(make_request())

    assert result == VALID_LOOK
    assert service.llm.calls["yandex"] == 1
    assert service.llm.calls["gigachat"] == 1


@pytest.mark.asyncio
async def test_call_llm_all_providers_fail_raises(service: Any) -> None:
    """Все провайдеры недоступны → поднимается последняя ошибка."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: сеть недоступна")

    service.llm = FakeLLM(["yandex", "gigachat"], handler)

    with pytest.raises(Exception) as exc_info:
        await service._call_llm(make_request())

    assert LLM_CLIENT_REQUEST_FAILED in str(exc_info.value)
    assert service.llm.calls["yandex"] == app_config["max_retries"]
    assert service.llm.calls["gigachat"] == app_config["max_retries"]
