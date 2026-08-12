"""Тесты конфигурации: базовые настройки и переопределения по APP_ENV."""

from config.base import BASE_CONFIG
from config.dev import DEV_CONFIG
from config.prod import PROD_CONFIG
from config.settings import ENV_CONFIGS, app_config


def test_base_config_has_common_settings() -> None:
    assert BASE_CONFIG["wait_time_base"] == 2
    assert BASE_CONFIG["temperature"] == 0.33
    assert BASE_CONFIG["max_tokens"] == 2000
    assert BASE_CONFIG["enabled_providers"] == ["yandex", "gigachat"]


def test_dev_overrides_max_retries_and_timeout() -> None:
    assert DEV_CONFIG["max_retries"] == 2
    assert DEV_CONFIG["timeout"] == 45


def test_prod_uses_current_settings() -> None:
    assert PROD_CONFIG["max_retries"] == 3
    assert PROD_CONFIG["timeout"] == 40


def test_env_configs_merge_base_settings() -> None:
    for config in (DEV_CONFIG, PROD_CONFIG):
        for key, value in BASE_CONFIG.items():
            assert config[key] == value


def test_active_config_matches_registered_env() -> None:
    assert ENV_CONFIGS["dev"] is DEV_CONFIG
    assert ENV_CONFIGS["prod"] is PROD_CONFIG
    assert app_config["enabled_providers"] == BASE_CONFIG["enabled_providers"]
