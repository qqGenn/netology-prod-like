"""
API роуты для ImageMaker сервиса.
"""

from typing import Annotated, Union

from fastapi import APIRouter, Body, status
from fastapi.responses import JSONResponse

from core.log import logger
from models.schemas import ApiResponseError, ApiResponseSuccess, LookCreate
from services.image_maker_service import ImageMakerService

router = APIRouter()

# Инициализируем сервис
image_maker_service = ImageMakerService()

# ========== Примеры для OpenAPI-контракта (Swagger) ==========

_REQUEST_EXAMPLES = {
    "Элегантный образ": {
        "summary": "Свидание в ресторане",
        "value": {
            "gender": "female",
            "age": 25,
            "style": "casual",
            "message": "Свидание в ресторане, хочу выглядеть стильно и элегантно",
        },
    },
    "Спортивный образ": {
        "summary": "Утренняя пробежка в парке",
        "value": {
            "gender": "male",
            "age": 30,
            "style": "sporty",
            "message": "Утренняя пробежка в парке, хочу выглядеть динамично",
        },
    },
}

_SUCCESS_RESPONSE_EXAMPLE = {
    "status": "success",
    "data": {
        "look_variants": [
            {
                "title": "Элегантный кэжуал для свидания",
                "target": "Выглядеть уместно и стильно в ресторане",
                "description": "Комбинация тёмных брюк чинос, струящейся блузы "
                "и лёгкого жакета. Дополните образ минималистичными украшениями "
                "и замшевыми лоферами.",
            },
            {
                "title": "Смарт-кэжуал",
                "target": "Сочетать комфорт и элегантность в вечерней обстановке",
                "description": "Классическая рубашка в приглушённых тонах с тёмными "
                "джинсами прямого кроя и кроссовками. Акцент — на качественных "
                "тканях и чистой гамме.",
            },
        ],
        "recommendation": "Отдайте предпочтение приглушённой палитре и чистым "
        "силуэтам, чтобы выглядеть уверенно и уместно.",
    },
}

_ERROR_RESPONSE_EXAMPLE = {
    "status": "error",
    "error_type": "internal",
    "message": "Сервис временно недоступен, попробуйте позже.",
}

_VALIDATION_RESPONSE_EXAMPLE = {
    "status": "error",
    "error_type": "validation",
    "message": "Ошибка значения 'style': значение 'sorty' недопустимо. "
    "Допустимые значения: 'sporty', 'casual', 'formal', 'informal' or 'eccentric'",
    "details": [
        {
            "field": "style",
            "error": "Ошибка значения 'style': значение 'sorty' недопустимо. "
            "Допустимые значения: 'sporty', 'casual', 'formal', "
            "'informal' or 'eccentric'",
        }
    ],
}

_INTERNAL_RESPONSE_EXAMPLE = {
    "status": "error",
    "error_type": "internal",
    "message": "Внутренняя ошибка сервера. Пожалуйста, попробуйте позже.",
}


@router.post(
    "/generate-look",
    status_code=status.HTTP_200_OK,
    summary="Генерация вариантов образов (луков)",
    description=(
        "Подбирает варианты образов по полу, возрасту, предпочитаемому стилю "
        "и описанию ситуации. Возвращает от 1 до 5 вариантов луков с целевым "
        "назначением и подробным описанием, а также общую рекомендацию."
    ),
    responses={
        200: {
            "description": "Успешная генерация образа. Тело ответа содержит "
            "либо результат генерации (status: 'success'), либо ошибку "
            "(status: 'error'), например при недоступности LLM-провайдера.",
            "content": {
                "application/json": {
                    "examples": {
                        "Успешный ответ": {
                            "summary": "Сгенерированные варианты образов",
                            "value": _SUCCESS_RESPONSE_EXAMPLE,
                        },
                        "Ошибка провайдера": {
                            "summary": "LLM-провайдер временно недоступен",
                            "value": _ERROR_RESPONSE_EXAMPLE,
                        },
                    }
                }
            },
        },
        422: {
            "model": ApiResponseError,
            "description": "Ошибка валидации запроса Pydantic (неверные поля "
            "или значения вне допустимых диапазонов).",
            "content": {
                "application/json": {
                    "examples": {
                        "Ошибка валидации": {
                            "summary": "Недопустимое значение поля",
                            "value": _VALIDATION_RESPONSE_EXAMPLE,
                        }
                    }
                }
            },
        },
        500: {
            "model": ApiResponseError,
            "description": "Внутренняя ошибка сервера.",
            "content": {
                "application/json": {
                    "examples": {
                        "Внутренняя ошибка": {
                            "summary": "Непредвиденная ошибка",
                            "value": _INTERNAL_RESPONSE_EXAMPLE,
                        }
                    }
                }
            },
        },
    },
)
async def generate_look(
    request: Annotated[
        LookCreate,
        Body(openapi_examples=_REQUEST_EXAMPLES),
    ]
) -> Union[ApiResponseSuccess, ApiResponseError]:
    """
    Генерация вариантов лука по описанию и выбранным параметрам.

    Args:
        request: Запрос с параметрами пользователя

    Returns:
        ApiResponseSuccess: Успешный ответ с вариантами луков
        ApiResponseError: Ответ с ошибкой
    """
    logger.info(
        "Получен запрос на генерацию образа",
        extra={
            "gender": request.gender.value,
            "age": request.age,
            "style": request.style.value,
            "message_length": len(request.message),
        },
    )

    try:
        return await image_maker_service.generate_look(request)
    except Exception as e:
        logger.error(f"Необработанная ошибка: {str(e)}", exc_info=True)
        # Response-экземпляр отдаётся FastAPI напрямую, без response_model
        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "error_type": "internal",
                "message": "Внутренняя ошибка сервера. Пожалуйста, попробуйте позже.",
            },
        )
