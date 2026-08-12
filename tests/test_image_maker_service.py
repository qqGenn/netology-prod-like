"""Тесты fallback, кэширования и ретраев ImageMakerService.

Вместо реального LLM-клиента используется FakeLLM с управляемым поведением
провайдеров, вместо CacheManager — in-memory FakeCache. Сетевая ошибка
(LLM_CLIENT_REQUEST_FAILED) должна ретраиться и приводить к fallback на
следующий провайдер, ошибка валидации — нет. Кэш-ключ строится по фактической
модели, поэтому при fallback ответ записывается под ключом secondary-модели.
"""

from typing import Any, Awaitable, Callable, Dict, Optional

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
        self.temperature = app_config["temperature"]

    def get_provider_chain(self) -> list:
        return list(self._chain)

    def get_provider_model(self, provider: str) -> str:
        return f"model-{provider}"

    def build_result_prompt(
        self, gender: str, age: int, style: str, message: str
    ) -> str:
        return f"{gender}|{age}|{style}|{message}"

    async def generate_looks_from_provider(self, provider: str, **kwargs: Any) -> dict:
        self.calls[provider] = self.calls.get(provider, 0) + 1
        return await self._handler(provider, **kwargs)


class FakeCache:
    """In-memory аналог CacheManager."""

    def __init__(self) -> None:
        self.store: Dict[str, dict] = {}
        self.writes: int = 0

    def get(self, key: str) -> Optional[dict]:
        return self.store.get(key)

    def set(self, key: str, data: dict) -> bool:
        self.writes += 1
        self.store[key] = data
        return True

    def delete(self, key: str) -> bool:
        return self.store.pop(key, None) is not None


@pytest.fixture
def service() -> Any:
    """Экземпляр ImageMakerService без инициализации реальных зависимостей."""
    service = ImageMakerService.__new__(ImageMakerService)
    service.cache = FakeCache()
    return service


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

    provider, request_hash, result, from_cache = await service._call_llm(make_request())

    assert result == VALID_LOOK
    assert provider == "gigachat"
    assert from_cache is False
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

    provider, request_hash, result, from_cache = await service._call_llm(make_request())

    assert result == VALID_LOOK
    assert provider == "yandex"
    assert from_cache is False
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

    provider, request_hash, result, from_cache = await service._call_llm(make_request())

    assert result == VALID_LOOK
    assert provider == "gigachat"
    assert from_cache is False
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


@pytest.mark.asyncio
async def test_call_llm_fallback_returns_secondary_model_hash(service: Any) -> None:
    """При фолбэке хэш-ключ строится по фактической модели (gigachat)."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        if provider == "yandex":
            raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: сеть недоступна")
        return VALID_LOOK

    service.llm = FakeLLM(["yandex", "gigachat"], handler)
    request = make_request()

    provider, request_hash, result, from_cache = await service._call_llm(request)

    assert provider == "gigachat"
    assert request_hash == service._generate_request_hash(request, "model-gigachat")
    assert request_hash != service._generate_request_hash(request, "model-yandex")
    assert from_cache is False


@pytest.mark.asyncio
async def test_call_llm_hits_secondary_cache_without_calling_llm(service: Any) -> None:
    """Кэш secondary (gigachat) проверяется до вызова: ответ из кэша, LLM не зовём."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: сеть недоступна")

    service.llm = FakeLLM(["yandex", "gigachat"], handler)
    request = make_request()
    secondary_hash = service._generate_request_hash(request, "model-gigachat")
    service.cache.set(secondary_hash, VALID_LOOK)

    provider, request_hash, result, from_cache = await service._call_llm(request)

    assert provider == "gigachat"
    assert request_hash == secondary_hash
    assert result == VALID_LOOK
    assert from_cache is True
    assert service.llm.calls["yandex"] == app_config["max_retries"]
    assert service.llm.calls.get("gigachat", 0) == 0


@pytest.mark.asyncio
async def test_call_llm_deletes_corrupt_cache_and_calls_llm(service: Any) -> None:
    """Битый кэш удаляется, запрос проваливается в LLM."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        return VALID_LOOK

    service.llm = FakeLLM(["yandex", "gigachat"], handler)
    request = make_request()
    primary_hash = service._generate_request_hash(request, "model-yandex")
    service.cache.set(primary_hash, {"broken": "data"})

    provider, request_hash, result, from_cache = await service._call_llm(request)

    assert provider == "yandex"
    assert request_hash == primary_hash
    assert result == VALID_LOOK
    assert from_cache is False
    assert primary_hash not in service.cache.store
    assert service.llm.calls["yandex"] == 1


@pytest.mark.asyncio
async def test_generate_look_fallback_caches_under_secondary_hash(service: Any) -> None:
    """End-to-end: при фолбэке generate_look пишет кэш под хэшем модели gigachat."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        if provider == "yandex":
            raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: сеть недоступна")
        return VALID_LOOK

    service.llm = FakeLLM(["yandex", "gigachat"], handler)
    request = make_request()

    response = await service.generate_look(request)

    assert response.status == "success"
    primary_hash = service._generate_request_hash(request, "model-yandex")
    secondary_hash = service._generate_request_hash(request, "model-gigachat")
    assert secondary_hash in service.cache.store
    assert primary_hash not in service.cache.store


@pytest.mark.asyncio
async def test_generate_look_does_not_rewrite_cache_on_hit(service: Any) -> None:
    """Кэш-хит не перезаписывает кэш-файл: set не вызывается."""

    async def handler(provider: str, **kwargs: Any) -> dict:
        raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: сеть недоступна")

    service.llm = FakeLLM(["yandex", "gigachat"], handler)
    request = make_request()
    secondary_hash = service._generate_request_hash(request, "model-gigachat")
    service.cache.set(secondary_hash, VALID_LOOK)
    writes_before = service.cache.writes

    response = await service.generate_look(request)

    assert response.status == "success"
    assert service.cache.writes == writes_before
    assert service.cache.store[secondary_hash] == VALID_LOOK
