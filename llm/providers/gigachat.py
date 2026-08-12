"""Провайдер GigaChat (OpenAI-совместимый API).

Особенность GigaChat: GIGACHAT_TOKEN в .env — это OAuth-клиентские данные
(base64 client_id:client_secret), а не access-токен. Access-токен живёт
~30 минут, поэтому перед каждым запросом он обновляется через OAuth.
"""

import os
import time
import uuid
from typing import Optional

import httpx
from openai import AsyncOpenAI

from core.log import logger
from llm.errors import LLM_CLIENT_REQUEST_FAILED


class GigaChatProvider:
    """Провайдер GigaChat с автообновлением OAuth access-токена."""

    name = "gigachat"

    def __init__(self, timeout: int) -> None:
        self.timeout = timeout
        self.auth_header = os.environ["GIGACHAT_TOKEN"]
        base_url = os.environ["GIGACHAT_BASE_URL"]
        self.oauth_url = os.environ["GIGACHAT_OAUTH_URL"]
        self.model = os.environ["GIGACHAT_MODEL"]
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=self.auth_header,
            timeout=timeout,
            max_retries=0,
            # В цепочке сертификатов Sber используется самоподписанный корневой CA
            http_client=httpx.AsyncClient(verify=False),
        )
        self._access_token: Optional[str] = None
        self._access_token_expires_at: float = 0.0

    def get_model_name(self) -> str:
        """Имя модели для логов."""
        return self.model

    def _is_token_valid(self) -> bool:
        """Проверяет, что access-токен ещё действителен (с запасом 60 сек)."""
        return bool(self._access_token) and time.time() < self._access_token_expires_at

    async def prepare_request(self) -> None:
        """Обновляет access-токен GigaChat через OAuth и подставляет его в клиент."""
        if self._is_token_valid():
            return

        async with httpx.AsyncClient(verify=False, timeout=self.timeout) as client:
            response = await client.post(
                self.oauth_url,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "RqUID": str(uuid.uuid4()),
                    "Authorization": f"Basic {self.auth_header}",
                },
                data={"scope": "GIGACHAT_API_PERS"},
            )

        if response.status_code != 200:
            logger.error(
                f"Ошибка получения OAuth-токена GigaChat "
                f"(HTTP {response.status_code}): {response.text[:500]}"
            )
            raise Exception(
                f"{LLM_CLIENT_REQUEST_FAILED}: не удалось получить OAuth-токен GigaChat"
            )

        try:
            payload = response.json()
            self._access_token = payload["access_token"]
            self._access_token_expires_at = payload.get("expires_at", 0) / 1000.0 - 60
        except (ValueError, KeyError) as e:
            logger.error(f"Некорректный ответ OAuth GigaChat: {response.text[:500]}")
            raise Exception(
                f"{LLM_CLIENT_REQUEST_FAILED}: некорректный ответ OAuth GigaChat"
            ) from e

        self.client.api_key = self._access_token
        logger.info("Обновлён access-токен GigaChat через OAuth")
