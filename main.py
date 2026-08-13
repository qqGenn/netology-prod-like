from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api import router
from config.settings import app_config  # noqa: F401 - импорт ради загрузки конфига
from core.log import logger

app = FastAPI(
    title="ImageMaker — AI-имиджмейкер",
    description="""
    ImageMaker — это интеллектуальный сервис на базе искусственного интеллекта,
    который помогает пользователям подобрать стильный образ (лук) на основе
    их индивидуальных характеристик. Пользователь указывает пол, возраст,
    предпочтительный стиль одежды и описывает ситуацию, для которой подбирается
    образ. Сервис генерирует несколько вариантов луков с подробным описанием,
    целевым назначением и общей рекомендацией.
    """,
    version="1.0.0",
)

# Роутер API
app.include_router(router, prefix="/api")


# Обработка ошибок валидации — возвращает ApiResponseError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Обработчик ошибок валидации с кастомными сообщениями."""
    errors = exc.errors()
    error = errors[0]
    field = error["loc"][-1] if error["loc"] else "unknown"

    msg = _build_validation_message(field, error)
    error_type = error.get("type", "unknown")

    # Лог валидационной ошибки — только в файл (DEBUG-уровень, не виден в консоли)
    logger.debug(f"Ошибка валидации (тип: {error_type}): {msg}")

    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error_type": "validation",
            "message": msg,
            "details": [
                {
                    "field": field,
                    "error": msg,
                }
            ],
        },
    )


def _build_validation_message(field: str, error: dict) -> str:
    """Собирает человекочитаемое сообщение об ошибке валидации поля."""
    error_type = error.get("type", "")
    ctx = error.get("ctx") or {}
    input_value = error.get("input")

    if error_type == "missing":
        return f"Обязательное поле '{field}' отсутствует"

    if error_type == "string_too_short":
        min_len = ctx.get("min_length", "N")
        return f"Ошибка значения '{field}': минимальная длина {min_len} символов"

    if error_type == "string_too_long":
        max_len = ctx.get("max_length", "N")
        return f"Ошибка значения '{field}': разрешено максимум {max_len} символов"

    if error_type == "enum":
        expected = ctx.get("expected", "неизвестные")
        invalid = f"'{input_value}'" if input_value is not None else "неизвестное"
        return (
            f"Ошибка значения '{field}': значение {invalid} недопустимо. "
            f"Допустимые значения: {expected}"
        )

    if error_type == "greater_than_equal":
        ge = ctx.get("ge", "N")
        return f"Ошибка значения '{field}': значение должно быть не меньше {ge}"

    if error_type == "less_than_equal":
        le = ctx.get("le", "N")
        return f"Ошибка значения '{field}': значение должно быть не больше {le}"

    if error_type == "int_parsing":
        return (
            f"Ошибка значения '{field}': ожидается целое число, "
            f"получено '{input_value}'"
        )

    if error_type == "int_type":
        return f"Ошибка значения '{field}': ожидается целое число"

    if error_type == "string_type":
        return f"Ошибка значения '{field}': ожидается строка"

    if error_type == "list_type":
        return f"Ошибка значения '{field}': ожидается список"

    if error_type == "too_short":
        min_len = ctx.get("min_length", "N")
        return f"Ошибка значения '{field}': должно быть не меньше {min_len} элементов"

    if error_type == "too_long":
        max_len = ctx.get("max_length", "N")
        return f"Ошибка значения '{field}': должно быть не больше {max_len} элементов"

    if error_type == "value_error":
        error_msg = str(ctx.get("error", "")) or "некорректное значение"
        return f"Ошибка значения '{field}': {error_msg}"

    # Для неизвестных типов используем человекочитаемое сообщение pydantic
    fallback = error.get("msg") or error_type
    return f"Ошибка значения '{field}': {fallback}"
