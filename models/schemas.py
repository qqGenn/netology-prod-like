"""
Pydantic модели для API запросов и ответов.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Gender(str, Enum):
    """Пол пользователя."""

    MALE = "male"
    FEMALE = "female"


class Style(str, Enum):
    """Стиль одежды."""

    SPORTY = "sporty"
    CASUAL = "casual"
    FORMAL = "formal"
    INFORMAL = "informal"
    ECCENTRIC = "eccentric"


# ========== Request Models ==========


class LookCreate(BaseModel):
    """Запрос на генерацию образа."""

    gender: Gender = Field(..., description="Пол пользователя: 'male' или 'female'")

    age: int = Field(
        ..., ge=10, le=100, description="Возраст пользователя (от 10 до 100 лет)"
    )

    style: Style = Field(..., description="Предпочитаемый стиль одежды")

    message: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Описание ситуации/повода (от 5 до 500 символов)",
    )

    @field_validator("age")
    @classmethod
    def validate_age(cls, v: int) -> int:
        """Дополнительная валидация возраста."""
        if v < 10 or v > 100:
            raise ValueError("Возраст должен быть от 10 до 100 лет")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        """Дополнительная валидация сообщения."""
        if not v.strip():
            raise ValueError("Сообщение не может быть пустым")
        return v.strip()


# ========== Response Models ==========


class LookVariant(BaseModel):
    """Вариант лука (образа)."""

    title: str = Field(
        ..., min_length=1, max_length=100, description="Название варианта / стиля"
    )

    target: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Цель, которую достигает пользователь (1-2 предложения)",
    )

    description: str = Field(
        ...,
        min_length=10,
        max_length=2000,
        description="Свободное описание лука (2 абзаца)",
    )


class LookData(BaseModel):
    """Данные с вариантами образов."""

    look_variants: List[LookVariant] = Field(
        ...,
        min_length=1,
        max_length=5,
        description="Массив вариантов луков (от 1 до 5)",
    )

    recommendation: str = Field(
        ...,
        min_length=10,
        max_length=1000,
        description="Краткая рекомендация-сводка (1 абзац)",
    )


# ========== API Response Wrappers ==========


class ValidationErrorDetail(BaseModel):
    """Детали ошибки валидации."""

    field: str = Field(..., description="Название поля, на котором произошла ошибка")

    error: str = Field(..., description="Сообщение об ошибке")


class ApiResponseSuccess(BaseModel):
    """Успешный ответ API."""

    status: str = Field(default="success", description="Статус операции")

    data: LookData = Field(..., description="Данные ответа")


class ApiResponseError(BaseModel):
    """Ответ API с ошибкой."""

    status: str = Field(default="error", description="Статус операции")

    error_type: str = Field(
        ..., description="Тип ошибки: 'validation', 'provider', 'internal' и т.д."
    )

    message: str = Field(..., description="Сообщение об ошибке")

    details: Optional[List[ValidationErrorDetail]] = Field(
        default=None, description="Детали ошибки (для валидационных ошибок)"
    )
