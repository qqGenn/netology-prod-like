"""Тесты конфигурации: разумные диапазоны и структура настроек по APP_ENV.

Точные значения конфигурации в тестах не зашиваются — параметры можно менять
(«шатать») в разумных пределах. Проверяются осмысленные диапазоны чисел,
наличие обязательных ключей и то, что enabled_providers — массив строк
(без привязки к конкретному порядку провайдеров).
"""

import pytest

from config.base import BASE_CONFIG
from config.dev import DEV_CONFIG
from config.prod import PROD_CONFIG
from config.settings import ENV_CONFIGS, REQUIRED_CONFIG_KEYS, app_config

# Параметры, присутствующие во всех конфигах (base + dev/prod)
COMMON_NUMERIC_KEYS = ("wait_time_base", "temperature", "max_tokens")
# Параметры, задаваемые только в dev/prod
PROVIDER_NUMERIC_KEYS = ("max_retries", "timeout")

ALL_CONFIGS = (BASE_CONFIG, DEV_CONFIG, PROD_CONFIG, app_config)
PROVIDER_CONFIGS = (DEV_CONFIG, PROD_CONFIG, app_config)


@pytest.mark.parametrize("config", ALL_CONFIGS)
@pytest.mark.parametrize("key", COMMON_NUMERIC_KEYS)
def test_common_numeric_settings_are_positive(config: dict, key: str) -> None:
    assert config[key] > 0


@pytest.mark.parametrize("config", PROVIDER_CONFIGS)
@pytest.mark.parametrize("key", PROVIDER_NUMERIC_KEYS)
def test_provider_numeric_settings_are_positive(config: dict, key: str) -> None:
    assert config[key] > 0


@pytest.mark.parametrize("config", ALL_CONFIGS)
def test_wait_time_base_below_ten(config: dict) -> None:
    assert 0 < config["wait_time_base"] < 10


@pytest.mark.parametrize("config", ALL_CONFIGS)
def test_temperature_below_one(config: dict) -> None:
    assert 0 < config["temperature"] < 1


@pytest.mark.parametrize("config", ALL_CONFIGS)
def test_max_tokens_below_ten_thousand(config: dict) -> None:
    assert 0 < config["max_tokens"] < 10000


@pytest.mark.parametrize("config", PROVIDER_CONFIGS)
def test_max_retries_at_most_five(config: dict) -> None:
    assert 0 < config["max_retries"] <= 5


@pytest.mark.parametrize("config", PROVIDER_CONFIGS)
def test_timeout_below_two_minutes(config: dict) -> None:
    assert 0 < config["timeout"] < 120


@pytest.mark.parametrize("config", ALL_CONFIGS)
def test_enabled_providers_is_non_empty_list_of_strings(config: dict) -> None:
    """Порядок провайдеров не проверяется — только тип и непустота массива."""
    providers = config["enabled_providers"]
    assert isinstance(providers, list)
    assert len(providers) > 0
    assert all(isinstance(p, str) and p for p in providers)


@pytest.mark.parametrize("config", PROVIDER_CONFIGS)
def test_env_configs_have_all_required_keys(config: dict) -> None:
    for key in REQUIRED_CONFIG_KEYS:
        assert key in config


def test_env_configs_include_base_keys() -> None:
    """dev/prod наследуют все ключи из base (без сверки значений)."""
    for config in (DEV_CONFIG, PROD_CONFIG):
        for key in BASE_CONFIG:
            assert key in config


def test_active_config_is_registered_env() -> None:
    assert ENV_CONFIGS["dev"] is DEV_CONFIG
    assert ENV_CONFIGS["prod"] is PROD_CONFIG
    assert app_config in ENV_CONFIGS.values()
