"""Провайдер Yandex AI Studio (OpenAI-совместимый API)."""

import os

from openai import AsyncOpenAI


class YandexProvider:
    """Провайдер Yandex AI Studio.

    Модель для API собирается как gpt://{folder_id}/{model}, при этом в логах
    используется только имя модели (get_model_name) без folder_id.
    """

    name = "yandex"

    def __init__(self, timeout: int) -> None:
        self.folder_id = os.environ["YANDEX_FOLDER_ID"]
        api_key = os.environ["YANDEX_API_KEY"]
        base_url = os.environ["YANDEX_BASE_URL"]
        self._model_name = os.environ["YANDEX_MODEL"]
        self.model = self._resolve_model()
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            max_retries=0,  # ретраями управляет сервис (tenacity)
        )

    def _resolve_model(self) -> str:
        """Собирает полный URI модели Yandex: gpt://{folder_id}/{model}.

        В .env задаётся только имя модели (например, deepseek-v4-flash),
        префикс gpt://{folder_id}/ собирается здесь.
        """
        if self._model_name.startswith("gpt://"):
            return self._model_name
        return f"gpt://{self.folder_id}/{self._model_name}"

    def get_model_name(self) -> str:
        """Имя модели для логов — без префикса gpt://{folder_id}."""
        return self._model_name

    async def prepare_request(self) -> None:
        """Yandex не требует подготовки перед запросом."""
        return None
