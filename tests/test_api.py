"""Тесты HTTP-эндпоинта /api/generate-look (без реальных нейросетей).

Проверяем HTTP 200 (успех) и 422 (ошибки валидации запроса).
"""

from typing import Any, Optional

import pytest
from fastapi.testclient import TestClient

import api.routes as routes
from models.schemas import ApiResponseSuccess, LookData, LookVariant


class FakeService:
    """Заглушка ImageMakerService с управляемым ответом или ошибкой."""

    def __init__(
        self,
        response: Optional[ApiResponseSuccess] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._response = response
        self._error = error

    async def generate_look(self, request: Any) -> Any:
        if self._error is not None:
            raise self._error
        return self._response


def _success_response() -> ApiResponseSuccess:
    return ApiResponseSuccess(
        status="success",
        data=LookData(
            look_variants=[
                LookVariant(
                    title="Элегантный кэжуал",
                    target="Выглядеть стильно в ресторане",
                    description="Тёмные брюки чинос, струящаяся блуза и лёгкий жакет.",
                )
            ],
            recommendation="Отдайте предпочтение приглушённой палитре "
            "и чистым силуэтам.",
        ),
    )


def test_generate_look_returns_200(
    client: TestClient, valid_request: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Корректный запрос → HTTP 200 с успешным ответом."""
    monkeypatch.setattr(routes, "image_maker_service", FakeService(_success_response()))

    resp = client.post("/api/generate-look", json=valid_request)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"]["look_variants"][0]["title"] == "Элегантный кэжуал"
    assert body["data"]["recommendation"]


@pytest.mark.parametrize(
    "payload, missing_field",
    [
        ({"gender": "female", "age": 25, "style": "casual"}, "message"),
        ({"gender": "female", "age": 25, "message": "Что-то надеть"}, "style"),
        ({"age": 25, "style": "casual", "message": "Что-то надеть"}, "gender"),
    ],
)
def test_generate_look_missing_field_returns_422(
    client: TestClient, payload: dict, missing_field: str
) -> None:
    """Отсутствующее обязательное поле → HTTP 422."""
    resp = client.post("/api/generate-look", json=payload)

    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "error"
    assert body["error_type"] == "validation"
    assert any(detail["field"] == missing_field for detail in body["details"])


@pytest.mark.parametrize(
    "payload",
    [
        {"gender": "alien", "age": 25, "style": "casual", "message": "Что-то надеть"},
        {"gender": "female", "age": 25, "style": "unknown", "message": "Что-то надеть"},
    ],
)
def test_generate_look_invalid_enum_returns_422(
    client: TestClient, payload: dict
) -> None:
    """Недопустимое значение enum (gender/style) → HTTP 422."""
    resp = client.post("/api/generate-look", json=payload)

    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "error"
    assert body["error_type"] == "validation"


@pytest.mark.parametrize("age", [5, 200])
def test_generate_look_age_out_of_range_returns_422(
    client: TestClient, valid_request: dict, age: int
) -> None:
    """Возраст вне диапазона 10–100 → HTTP 422."""
    payload = {**valid_request, "age": age}

    resp = client.post("/api/generate-look", json=payload)

    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "error"
    assert body["error_type"] == "validation"
    assert any(detail["field"] == "age" for detail in body["details"])


def test_generate_look_message_too_short_returns_422(
    client: TestClient, valid_request: dict
) -> None:
    """Сообщение короче 5 символов → HTTP 422."""
    payload = {**valid_request, "message": "абв"}

    resp = client.post("/api/generate-look", json=payload)

    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "error"
    assert body["error_type"] == "validation"
    assert any(detail["field"] == "message" for detail in body["details"])


def test_generate_look_service_error_returns_500(
    client: TestClient, valid_request: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Исключение в сервисе → HTTP 500 с телом ошибки (error_type='internal')."""
    monkeypatch.setattr(
        routes,
        "image_maker_service",
        FakeService(error=RuntimeError("boom")),
    )

    resp = client.post("/api/generate-look", json=valid_request)

    assert resp.status_code == 500
    body = resp.json()
    assert body["status"] == "error"
    assert body["error_type"] == "internal"
    assert isinstance(body["message"], str) and body["message"]
