import hashlib
import json
from typing import Union

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from cache.cache_manager import CacheManager
from config.settings import json_config
from llm.llm_client import (
    LLMClient,
    LLM_CLIENT_VALIDATION_ERROR,
    LLM_CLIENT_JSON_PARSE_ERROR,
    LLM_CLIENT_REQUEST_FAILED,
)
from core.log import logger
from models.schemas import LookCreate, LookData, ApiResponseSuccess, ApiResponseError


def _is_retryable_error(exc: BaseException) -> bool:
    """Сетевая ошибка (LLM_CLIENT_REQUEST_FAILED) подлежит ретраю."""
    return str(exc).startswith(LLM_CLIENT_REQUEST_FAILED)


def _log_retry(retry_state) -> None:
    """before_sleep-логгер: модель, номер попытки, осталось попыток."""
    service = retry_state.args[0]
    provider = retry_state.args[1]
    model = service.llm.get_provider_model(provider)
    attempt = retry_state.attempt_number
    max_attempts = retry_state.retry_object.stop.max_attempt_number
    remaining = max_attempts - attempt
    logger.warning(
        f"Ретрай LLM-запроса: модель={model!r}, "
        f"попытка {attempt}/{max_attempts}, осталось попыток: {remaining}. "
        f"Ошибка: {retry_state.outcome.exception()}"
    )


class ImageMakerService:
    """Сервис для генерации образов с использованием LLM и кэширования."""

    def __init__(self):
        self.cache = CacheManager()
        self.llm = LLMClient()

    @retry(
        stop=stop_after_attempt(json_config.get("max_retries", 3)),
        wait=wait_exponential(
            multiplier=json_config.get("wait_time_base", 2), min=1, max=60
        ),
        retry=retry_if_exception(_is_retryable_error),
        before_sleep=_log_retry,
        reraise=True,
    )
    async def _call_provider(self, provider: str, request: LookCreate) -> dict:
        """Запрос к конкретному провайдеру с ретраями (через tenacity)."""
        return await self.llm.generate_looks_from_provider(
            provider,
            gender=request.gender.value,
            age=request.age,
            style=request.style.value,
            message=request.message,
        )

    async def _call_llm(self, request: LookCreate) -> dict:
        """Мастер-функция: идём по цепочке провайдеров, пока один не ответит.

        Сначала primary (нулевой индекс enabled_providers); если он упал,
        переключаемся на следующий провайдер (secondary). Если все провайдеры
        недоступны — пробрасываем ошибку.
        """
        providers = self.llm.get_provider_chain()
        if not providers:
            raise Exception(
                f"{LLM_CLIENT_REQUEST_FAILED}: нет доступных провайдеров LLM"
            )

        last_error: Union[Exception, None] = None

        for idx, provider in enumerate(providers):
            try:
                return await self._call_provider(provider, request)
            except Exception as e:
                last_error = e
                if idx + 1 < len(providers):
                    next_provider = providers[idx + 1]
                    logger.warning(
                        f"Провайдер {provider!r} "
                        f"(модель {self.llm.get_provider_model(provider)}) "
                        f"недоступен. Переключаемся на следующий провайдер "
                        f"{next_provider!r} (модель "
                        f"{self.llm.get_provider_model(next_provider)}). "
                        f"Ошибка: {e}"
                    )

        raise last_error  # type: ignore[misc]

    async def generate_look(
        self, request: LookCreate
    ) -> Union[ApiResponseSuccess, ApiResponseError]:
        """
        Получить ответ от LLM с генерацией вариантов образов.

        Args:
            request: Валидированный запрос от пользователя

        Returns:
            ApiResponseSuccess при успехе или ApiResponseError при ошибке
        """
        request_data = request.model_dump()
        logger.info(f"Входящий запрос: {json.dumps(request_data, ensure_ascii=False)}")

        # Формируем хэш-ключ запроса
        request_hash = self._generate_request_hash(request)
        logger.info(f"Сформирован хэш-ключ запроса: {request_hash}")

        # Проверяем наличие в кэше
        cached_data = self.cache.get(request_hash)
        if cached_data is not None:
            logger.info(f"Найдены данные в кэше по ключу: {request_hash}")
            try:
                image_data = LookData(**cached_data)
                return ApiResponseSuccess(status="success", data=image_data)
            except Exception as e:
                logger.error(f"Ошибка валидации кэшированных данных: {e}")
                return ApiResponseError(
                    status="error",
                    error_type="internal",
                    message=f"Некорректные данные в кэше: {str(e)}",
                )

        logger.info(f"Отправляем запрос в LLM по ключу: {request_hash}")

        # Отправляем запрос в LLM с ретраями через tenacity
        try:
            llm_response = await self._call_llm(request)
            logger.info(f"Получен ответ от LLM для ключа: {request_hash}")
        except Exception as e:
            logger.error(f"Ошибка при обращении к LLM: {e}")
            error_msg = str(e)

            if error_msg.startswith(LLM_CLIENT_VALIDATION_ERROR):
                return ApiResponseError(
                    status="error",
                    error_type="internal",
                    message="Ошибка валидации ответа LLM (неверный формат данных), "
                    "попробуйте снова, если ошибка повторяется - обратитесь в техподдержку.",
                )

            if error_msg.startswith(LLM_CLIENT_JSON_PARSE_ERROR):
                return ApiResponseError(
                    status="error",
                    error_type="internal",
                    message="Ошибка обработки данных, попробуйте снова через некоторое "
                    "время или обратитесь в техподдержку.",
                )

            if error_msg.startswith(LLM_CLIENT_REQUEST_FAILED):
                return ApiResponseError(
                    status="error",
                    error_type="internal",
                    message="Сервис временно недоступен, попробуйте позже.",
                )

            return ApiResponseError(
                status="error",
                error_type="internal",
                message="Ошибка при обращении к LLM, попробуйте снова через некоторое "
                "время или обратитесь в техподдержку.",
            )

        # Проверка структуры ответа от LLM
        try:
            image_data = LookData(**llm_response)
            logger.info("Ответ от LLM успешно валидирован как LookData")
        except Exception as e:
            logger.error(f"Некорректная структура ответа от LLM: {e}")
            return ApiResponseError(
                status="error",
                error_type="internal",
                message=f"Некорректная структура ответа от LLM: {str(e)}",
            )

        # Записываем в кэш
        try:
            self.cache.set(request_hash, image_data.model_dump())
            logger.info(f"Данные успешно записаны в кэш по ключу: {request_hash}")
        except Exception as e:
            logger.error(f"Ошибка при записи в кэш: {e}")
            # Возвращаем данные, даже если кэширование не удалось
            return ApiResponseSuccess(status="success", data=image_data)

        return ApiResponseSuccess(status="success", data=image_data)

    def _generate_request_hash(self, request: LookCreate) -> str:
        """Генерирует хэш-ключ на основе итогового промпта, модели и температуры.

        В хэше учитываются параметры пользователя, т.к. result_prompt
        собирается подстановкой данных запроса в шаблон системного промпта.
        """
        result_prompt = self.llm.build_result_prompt(
            gender=request.gender.value,
            age=request.age,
            style=request.style.value,
            message=request.message,
        )
        hash_data = {
            "result_prompt": result_prompt,
            "model_name": self.llm.model_name,
            "temperature": self.llm.temperature,
        }
        request_json = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(request_json.encode()).hexdigest()
