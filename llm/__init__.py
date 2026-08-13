"""Клиент LLM приложения."""

from llm.llm_client import (
    LLM_CLIENT_JSON_PARSE_ERROR,
    LLM_CLIENT_REQUEST_FAILED,
    LLM_CLIENT_VALIDATION_ERROR,
    LLMClient,
)

__all__ = [
    "LLMClient",
    "LLM_CLIENT_VALIDATION_ERROR",
    "LLM_CLIENT_JSON_PARSE_ERROR",
    "LLM_CLIENT_REQUEST_FAILED",
]
