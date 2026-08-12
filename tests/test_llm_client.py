"""Тесты формирования промптов и цепочки провайдеров LLM-клиента."""

from config.settings import app_config
from llm.llm_client import LLMClient
from llm.system_prompt import system_prompt as SYSTEM_PROMPT_TEMPLATE


def _make_light_client() -> LLMClient:
    """Лёгкий экземпляр без инициализации провайдеров."""
    client = LLMClient.__new__(LLMClient)
    client.system_prompt_template = SYSTEM_PROMPT_TEMPLATE
    return client


def test_build_result_prompt_substitutes_user_fields() -> None:
    client = _make_light_client()

    result = client.build_result_prompt(
        gender="female", age=25, style="casual", message="Свидание в ресторане"
    )

    assert "female" in result
    assert "25" in result
    assert "casual" in result
    assert "Свидание в ресторане" in result


def test_build_result_prompt_has_no_leftover_placeholders() -> None:
    client = _make_light_client()

    result = client.build_result_prompt(
        gender="male", age=30, style="formal", message="Важная встреча"
    )

    for placeholder in ("{gender}", "{age}", "{style}", "{user_message}"):
        assert placeholder not in result


def test_build_result_prompt_contains_json_structure() -> None:
    client = _make_light_client()

    result = client.build_result_prompt(
        gender="female", age=25, style="casual", message="Вечерний выход"
    )

    assert '"look_variants"' in result
    assert '"recommendation"' in result


def test_provider_chain_order_matches_config() -> None:
    """Порядок цепочки провайдеров соответствует enabled_providers из конфига."""
    client = LLMClient()

    assert client.get_provider_chain() == app_config["enabled_providers"]
