"""Коды ошибок LLM-клиента.

Вынесены в отдельный модуль, чтобы провайдеры (llm.providers.*) могли
использовать их без циклического импорта с llm.llm_client.
"""

LLM_CLIENT_VALIDATION_ERROR = "LLM_CLIENT_VALIDATION_ERROR"
LLM_CLIENT_JSON_PARSE_ERROR = "LLM_CLIENT_JSON_PARSE_ERROR"
LLM_CLIENT_REQUEST_FAILED = "LLM_CLIENT_REQUEST_FAILED"
