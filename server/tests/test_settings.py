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


@pytest.mark.parametrize(
    "raw, expected",
    [("false", False), ("true", True), ("0", False), ("1", True)],
)
def test_cookie_secure_string_parsing(monkeypatch, raw, expected):
    monkeypatch.setenv("AUTH_PASSWORD", "pw")
    monkeypatch.setenv("MQTT_HOST", "broker")
    monkeypatch.setenv("COOKIE_SECURE", raw)
    s = Settings(_env_file=None)
    assert s.cookie_secure is expected


def test_auth_password_set_but_mqtt_host_missing(monkeypatch):
    # Required-field asymmetry: AUTH_PASSWORD present, MQTT_HOST missing -> fails.
    monkeypatch.setenv("AUTH_PASSWORD", "pw")
    monkeypatch.delenv("MQTT_HOST", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_mqtt_host_set_but_auth_password_missing(monkeypatch):
    # The reverse: MQTT_HOST present, AUTH_PASSWORD missing -> fails.
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)
    monkeypatch.setenv("MQTT_HOST", "broker")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
