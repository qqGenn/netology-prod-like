"""
LLM Client — унифицированный клиент для работы с AI-провайдерами через OpenAI-совместимый API.

Оркестрирует запросы к провайдерам из реестра llm.providers
(сейчас Yandex AI Studio и GigaChat). Провайдер-специфичная логика
(сборка клиента, OAuth-токен и т.п.) вынесена в соответствующие модули.

Обработка ошибок:
- сетевые/временные ошибки      -> LLM_CLIENT_REQUEST_FAILED  (подлежат ретраю на уровне сервиса)
- невалидный JSON в ответе      -> LLM_CLIENT_JSON_PARSE_ERROR
- невалидная структура ответа   -> LLM_CLIENT_VALIDATION_ERROR
"""

import json
import time
from typing import Any, Dict, Optional

from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from core.log import logger
from config.settings import json_config
from llm.errors import (
    LLM_CLIENT_VALIDATION_ERROR,
    LLM_CLIENT_JSON_PARSE_ERROR,
    LLM_CLIENT_REQUEST_FAILED,
)
from llm.providers import PROVIDERS, build_provider
from llm.providers.base import LLMProvider
from llm.system_prompt import system_prompt as SYSTEM_PROMPT_TEMPLATE

# Коды ошибок для LLM клиента
PROVIDER_YANDEX = "yandex"
PROVIDER_GIGACHAT = "gigachat"

# Типы временных ошибок, после которых стоит попробовать другого провайдера
_TRANSIENT_ERRORS = (
    APITimeoutError,
    APIConnectionError,
    RateLimitError,
    InternalServerError,
)


class LLMClient:
    """Клиент для взаимодействия с LLM-провайдерами через OpenAI-совместимый API."""

    def __init__(self):
        self.temperature = float(json_config["temperature"])
        self.timeout = int(json_config["timeout"])
        self.max_tokens = int(json_config["max_tokens"])
        self.system_prompt_template = SYSTEM_PROMPT_TEMPLATE

        self._providers: Dict[str, LLMProvider] = {}
        self._clients: Dict[str, AsyncOpenAI] = {}
        for name in json_config["enabled_providers"]:
            if name not in PROVIDERS:
                raise RuntimeError(f"Неизвестный LLM-провайдер: {name!r}")
            provider = build_provider(name, self.timeout)
            self._providers[name] = provider
            self._clients[name] = provider.client
            logger.info(
                f"Инициализирован клиент {name}, модель: {provider.get_model_name()}"
            )

        if not self._providers:
            raise RuntimeError(
                "Не удалось инициализировать ни одного AI-провайдера. "
                "Проверьте enabled_providers в config/main.json и ключи в .env"
            )

        # Полный URI модели Yandex сохраняется отдельно: используется в ключе кэша
        yandex = self._providers.get(PROVIDER_YANDEX)
        self.model_name: Optional[str] = yandex.model if yandex else None

        logger.info(
            f"Инициализирован LLMClient. "
            f"провайдеры: {list(self._providers.keys())}, температура: {self.temperature}"
        )

    def build_result_prompt(self, gender: str, age: int, style: str, message: str) -> str:
        """Собирает итоговый системный промпт (result_prompt).

        Подставляет данные пользователя в шаблон system_prompt_template.
        """
        return (
            self.system_prompt_template.replace("{gender}", str(gender))
            .replace("{age}", str(age))
            .replace("{style}", str(style))
            .replace("{user_message}", str(message))
        )

    def get_provider_chain(self) -> list:
        """Список инициализированных провайдеров в порядке приоритета.

        Приоритет задаётся порядком в enabled_providers из config:
        primary — нулевой индекс, secondary — следующий, и т.д.
        """
        enabled = json_config["enabled_providers"]
        return [p for p in enabled if p in self._providers]

    def get_provider_model(self, provider: str) -> str:
        """Вернуть имя модели (без префикса gpt://{folder_id}) для указанного провайдера."""
        return self._providers[provider].get_model_name()

    async def generate_looks_from_provider(
        self, provider: str, gender: str, age: int, style: str, message: str
    ) -> Dict[str, Any]:
        """Отправить запрос к конкретному провайдеру без ретраев и фолбэка.

        Возвращает {"look_variants": [...], "recommendation": "..."}
        или выбрасывает Exception с префиксами LLM_CLIENT_*.
        """
        if provider not in self._clients:
            raise Exception(
                f"{LLM_CLIENT_REQUEST_FAILED}: провайдер '{provider}' недоступен"
            )

        result_prompt = self.build_result_prompt(gender, age, style, message)
        return await self._request_with_validation(provider, result_prompt, message)

    async def _request_with_validation(
        self, provider: str, result_prompt: str, user_message: str
    ) -> Dict[str, Any]:
        """Запрос к конкретному провайдеру с парсингом и валидацией ответа."""
        client = self._clients[provider]
        provider_obj = self._providers[provider]

        await provider_obj.prepare_request()

        start_time = time.time()
        try:
            response = await client.chat.completions.create(
                model=provider_obj.model,
                messages=[
                    {"role": "system", "content": result_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except _TRANSIENT_ERRORS as e:
            logger.warning(f"Временная сетевая ошибка от '{provider}': {e}")
            raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: {e}") from e
        except APIStatusError as e:
            logger.error(f"Ошибка API от '{provider}' (HTTP {e.status_code}): {e}")
            raise Exception(f"Ошибка API от '{provider}': {e}") from e
        except Exception as e:
            logger.error(f"Неожиданная ошибка от '{provider}': {e}")
            raise

        if (
            not response.choices
            or not response.choices[0].message
            or not response.choices[0].message.content
        ):
            raise Exception(f"{LLM_CLIENT_REQUEST_FAILED}: пустой ответ от LLM")

        content = response.choices[0].message.content

        elapsed_time = time.time() - start_time
        logger.info(
            f"Ответ от провайдера '{provider}' "
            f"(модель {provider_obj.get_model_name()}) получен за "
            f"{elapsed_time:.3f} сек, длина ответа: {len(content)} символов"
        )

        return self._parse_and_validate(content)

    def _parse_and_validate(self, content: str) -> Dict[str, Any]:
        """Парсинг JSON-ответа и проверка структуры look_variants/recommendation."""
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"{LLM_CLIENT_JSON_PARSE_ERROR}: {e}")
            raise Exception(
                f"{LLM_CLIENT_JSON_PARSE_ERROR}: некорректный формат JSON"
            ) from e

        if not isinstance(data, dict):
            logger.error(f"{LLM_CLIENT_VALIDATION_ERROR}: ответ не является объектом")
            raise Exception(
                f"{LLM_CLIENT_VALIDATION_ERROR}: ответ не является объектом"
            )

        look_variants = data.get("look_variants")
        if not isinstance(look_variants, list) or not look_variants:
            logger.error(
                f"{LLM_CLIENT_VALIDATION_ERROR}: отсутствует или некорректно поле 'look_variants'"
            )
            raise Exception(
                f"{LLM_CLIENT_VALIDATION_ERROR}: отсутствует или некорректно поле 'look_variants'"
            )

        for variant in look_variants:
            if not isinstance(variant, dict):
                raise Exception(
                    f"{LLM_CLIENT_VALIDATION_ERROR}: элемент look_variants не является объектом"
                )
            for field in ("title", "target", "description"):
                if field not in variant or not isinstance(variant[field], str):
                    raise Exception(
                        f"{LLM_CLIENT_VALIDATION_ERROR}: в элементе look_variants "
                        f"отсутствует строковое поле '{field}'"
                    )

        recommendation = data.get("recommendation")
        if not isinstance(recommendation, str):
            raise Exception(
                f"{LLM_CLIENT_VALIDATION_ERROR}: отсутствует или некорректно поле 'recommendation'"
            )

        return {
            "look_variants": [
                {
                    "title": variant["title"].strip(),
                    "target": variant["target"].strip(),
                    "description": variant["description"].strip(),
                }
                for variant in look_variants
            ],
            "recommendation": recommendation.strip(),
        }
