import os

# Required env must exist before importing src.* (Settings() runs at import time).
os.environ.setdefault("AUTH_PASSWORD", "test-password")
os.environ.setdefault("MQTT_HOST", "localhost")
# Plain-HTTP TestClient must keep the session cookie -> disable the Secure flag.
os.environ.setdefault("COOKIE_SECURE", "false")

import pytest
from fastapi.testclient import TestClient

from src import api
from src.mqtt_client import device_states, topic_values

TEST_PASSWORD = "test-password"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Redirect runtime state to a temp dir so tests never touch real data/.
    monkeypatch.setattr(api.settings, "config_path", str(tmp_path / "config.json"))
    monkeypatch.setattr(api, "ICON_PATH", tmp_path / "icon.png")
    # Clear both global caches so state never leaks across tests.
    device_states.clear()
    topic_values.clear()
    # No `with` -> lifespan (and the MQTT listener task) is not started.
    return TestClient(api.app)


@pytest.fixture()
def auth_client(client):
    resp = client.post("/api/login", json={"password": TEST_PASSWORD})
    assert resp.status_code == 200
    return client
