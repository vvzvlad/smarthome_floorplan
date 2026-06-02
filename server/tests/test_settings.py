import pytest
from pydantic import ValidationError

from src.settings import Settings


def test_missing_required_fields_fail(monkeypatch):
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("MQTT_HOST", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_defaults_and_secret_fallback(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "pw")
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    # conftest sets COOKIE_SECURE=false for the TestClient; clear it here so this
    # test verifies the field's real default rather than the inherited env value.
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    s = Settings(_env_file=None)
    assert s.mqtt_port == 1883
    assert s.cookie_secure is True
    assert s.config_path == "data/config.json"
    assert s.effective_secret_key == "pw"  # falls back to auth_password


def test_explicit_secret_key(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "pw")
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("SECRET_KEY", "explicit")
    s = Settings(_env_file=None)
    assert s.effective_secret_key == "explicit"


def test_log_level_normalized(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "pw")
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    s = Settings(_env_file=None)
    assert s.log_level == "DEBUG"


def test_log_level_invalid_rejected(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD", "pw")
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("LOG_LEVEL", "verbose")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
