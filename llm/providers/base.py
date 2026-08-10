"""Базовый интерфейс LLM-провайдера.

Все провайдеры реализуют единый контракт, что позволяет llm.llm_client
работать с ними унифицированно (сборка клиента, имя модели, подготовка запроса).
"""

from typing import Protocol, runtime_checkable

from openai import AsyncOpenAI


@runtime_checkable
class LLMProvider(Protocol):
    """Единый интерфейс для всех LLM-провайдеров."""

    name: str
    model: str
    client: AsyncOpenAI

    def get_model_name(self) -> str:
        """Имя модели для логов — без приватных данных (например, без gpt://{folder_id})."""
        ...

    async def prepare_request(self) -> None:
        """Подготовка перед запросом (например, обновление access-токена)."""
        ...
