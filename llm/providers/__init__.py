"""Реестр LLM-провайдеров.

Новый провайдер добавляется одним классом в этот пакет и автоматически
попадает в реестр по своему атрибуту name.
"""

from llm.providers.base import LLMProvider
from llm.providers.gigachat import GigaChatProvider
from llm.providers.yandex import YandexProvider

PROVIDERS = {provider.name: provider for provider in (YandexProvider, GigaChatProvider)}

__all__ = [
    "LLMProvider",
    "YandexProvider",
    "GigaChatProvider",
    "PROVIDERS",
    "build_provider",
]


def build_provider(name: str, timeout: int) -> LLMProvider:
    """Создаёт экземпляр провайдера по имени (ключу enabled_providers)."""
    if name not in PROVIDERS:
        raise RuntimeError(f"Неизвестный LLM-провайдер: {name!r}")
    return PROVIDERS[name](timeout=timeout)
