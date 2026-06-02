import pytest

from src import api
from src.mqtt_client import device_states

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def test_info_public(client):
    resp = client.get("/api/info")
    assert resp.status_code == 200
    assert "title" in resp.json()


def test_session_public_unauthenticated(client):
    resp = client.get("/api/session")
    assert resp.status_code == 200
    assert resp.json() == {"auth": False}


def test_config_requires_auth(client):
    assert client.get("/api/config").status_code == 401


def test_login_wrong_password(client):
    assert client.post("/api/login", json={"password": "nope"}).status_code == 401


def test_login_malformed_body(client):
    # Non-JSON body -> 400, never 500
    resp = client.post("/api/login", content=b"not-json",
                       headers={"Content-Type": "application/json"})
    assert resp.status_code == 400


def test_login_then_access(auth_client):
    assert auth_client.get("/api/session").json() == {"auth": True}
    assert auth_client.get("/api/config").status_code == 200


def test_logout_clears_session(auth_client):
    auth_client.post("/api/logout")
    assert auth_client.get("/api/config").status_code == 401


def test_command_on(auth_client, monkeypatch):
    sent = {}

    async def fake_publish_command(entity, state):
        sent["entity"], sent["state"] = entity, state

    monkeypatch.setattr(api, "publish_command", fake_publish_command)
    resp = auth_client.post("/api/entity/Lamp/command", json={"state": "on"})
    assert resp.status_code == 200
    assert sent == {"entity": "Lamp", "state": "ON"}
    assert device_states["Lamp"] == {"state": "ON"}


def test_command_bad_state(auth_client):
    assert auth_client.post("/api/entity/Lamp/command",
                            json={"state": "blink"}).status_code == 400


def test_command_bool_value_rejected(auth_client):
    # bool must be rejected even though it is a subclass of int
    assert auth_client.post("/api/entity/Lamp/command",
                            json={"field": "brightness", "value": True}).status_code == 400


def test_command_numeric_value(auth_client, monkeypatch):
    async def fake_publish_value(entity, field, value):
        pass

    monkeypatch.setattr(api, "publish_value", fake_publish_value)
    resp = auth_client.post("/api/entity/Lamp/command",
                            json={"field": "brightness", "value": 128})
    assert resp.status_code == 200
    assert device_states["Lamp"]["brightness"] == 128


def test_icon_rejects_non_png(auth_client):
    resp = auth_client.post("/api/icon", content=b"notpng",
                            headers={"Content-Type": "image/png"})
    assert resp.status_code == 400


def test_icon_upload_and_status(auth_client):
    assert auth_client.get("/api/icon").json() == {"custom": False}
    assert auth_client.post("/api/icon", content=_PNG,
                            headers={"Content-Type": "image/png"}).status_code == 200
    assert auth_client.get("/api/icon").json() == {"custom": True}
    # Public icon endpoint now serves the uploaded custom icon
    assert client_get_icon(auth_client).status_code == 200
    assert auth_client.delete("/api/icon").status_code == 200
    assert auth_client.get("/api/icon").json() == {"custom": False}


def client_get_icon(c):
    return c.get("/apple-touch-icon.png")
