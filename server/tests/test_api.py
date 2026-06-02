import pytest

from src import api
from src.mqtt_client import device_states

# Must match conftest.TEST_PASSWORD / the AUTH_PASSWORD set in conftest.
TEST_PASSWORD = "test-password"

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16


def _number_config(read_topic="sensors/temp", write_topic="cmd/topic"):
    """Minimal config with one number widget so read/write topics are configured."""
    return {
        "id": "x",
        "name": "Plan",
        "imageBase64": "",
        "entities": [
            {
                "type": "number",
                "numberConfig": {"readTopic": read_topic, "writeTopic": write_topic},
            }
        ],
    }


def _button_config(topic="btn/topic", value="ON", text="Send"):
    """Minimal config with one button widget so its topic is allow-listed."""
    return {
        "id": "x",
        "name": "Plan",
        "imageBase64": "",
        "entities": [
            {
                "type": "button",
                "buttonConfig": {"topic": topic, "value": value, "text": text},
            }
        ],
    }


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


# --------------------------------------------------------------------------- #
# POST /api/config
# --------------------------------------------------------------------------- #
def test_config_requires_auth_post(client):
    assert client.post("/api/config", json=_number_config()).status_code == 401


def test_config_persists_and_read_back(auth_client):
    cfg = _number_config()
    assert auth_client.post("/api/config", json=cfg).status_code == 200
    assert auth_client.get("/api/config").json() == cfg


def test_config_no_restart_when_read_topics_unchanged(auth_client, monkeypatch):
    called = {"n": 0}

    async def fake_restart():
        called["n"] += 1

    # Install the spy BEFORE any POST so the real _restart_mqtt_listener (which
    # spawns a real MQTT task and would leave an orphaned pending task) is never
    # called. The seeding POST below changes read topics from empty -> one call.
    monkeypatch.setattr(api, "_restart_mqtt_listener", fake_restart)
    # Seed an initial config; this changes read topics from empty (one restart).
    auth_client.post("/api/config", json=_number_config(read_topic="sensors/temp"))
    # Reset so the assertion isolates the "unchanged" case below.
    called["n"] = 0
    # Same read topic, different unrelated field -> no restart
    cfg2 = _number_config(read_topic="sensors/temp")
    cfg2["name"] = "Renamed"
    assert auth_client.post("/api/config", json=cfg2).status_code == 200
    assert called["n"] == 0


def test_config_restart_when_read_topics_changed(auth_client, monkeypatch):
    called = {"n": 0}

    async def fake_restart():
        called["n"] += 1

    # Install the spy BEFORE any POST so no real restart task is ever created.
    monkeypatch.setattr(api, "_restart_mqtt_listener", fake_restart)
    # Seed an initial config (changes read topics from empty).
    auth_client.post("/api/config", json=_number_config(read_topic="sensors/temp"))
    # Reset so the assertion isolates the "changed" case below.
    called["n"] = 0
    assert auth_client.post(
        "/api/config", json=_number_config(read_topic="sensors/humidity")
    ).status_code == 200
    assert called["n"] == 1


# --------------------------------------------------------------------------- #
# POST /api/mqtt/publish
# --------------------------------------------------------------------------- #
def test_mqtt_publish_topic_not_configured_403(auth_client, monkeypatch):
    async def fake_publish_raw(topic, value):
        pass

    monkeypatch.setattr(api, "publish_raw", fake_publish_raw)
    # No config written -> no configured write topics
    resp = auth_client.post("/api/mqtt/publish", json={"topic": "any/topic", "value": "1"})
    assert resp.status_code == 403


def test_mqtt_publish_blank_topic_400(auth_client):
    assert auth_client.post(
        "/api/mqtt/publish", json={"topic": "   ", "value": "1"}
    ).status_code == 400


def test_mqtt_publish_bool_value_400(auth_client):
    auth_client.post("/api/config", json=_number_config(write_topic="cmd/topic"))
    assert auth_client.post(
        "/api/mqtt/publish", json={"topic": "cmd/topic", "value": True}
    ).status_code == 400


def test_mqtt_publish_list_value_400(auth_client):
    auth_client.post("/api/config", json=_number_config(write_topic="cmd/topic"))
    assert auth_client.post(
        "/api/mqtt/publish", json={"topic": "cmd/topic", "value": [1, 2]}
    ).status_code == 400


def test_mqtt_publish_numeric_value_coerced(auth_client, monkeypatch):
    sent = {}

    async def fake_publish_raw(topic, value):
        sent["topic"], sent["value"] = topic, value

    monkeypatch.setattr(api, "publish_raw", fake_publish_raw)
    auth_client.post("/api/config", json=_number_config(write_topic="cmd/topic"))
    resp = auth_client.post("/api/mqtt/publish", json={"topic": "cmd/topic", "value": 42})
    assert resp.status_code == 200
    # Numeric value coerced to string and forwarded
    assert sent == {"topic": "cmd/topic", "value": "42"}


def test_mqtt_publish_happy_string(auth_client, monkeypatch):
    sent = {}

    async def fake_publish_raw(topic, value):
        sent["topic"], sent["value"] = topic, value

    monkeypatch.setattr(api, "publish_raw", fake_publish_raw)
    auth_client.post("/api/config", json=_number_config(write_topic="cmd/topic"))
    resp = auth_client.post("/api/mqtt/publish", json={"topic": "cmd/topic", "value": "hi"})
    assert resp.status_code == 200
    assert sent == {"topic": "cmd/topic", "value": "hi"}


def test_mqtt_publish_button_topic_allowed(auth_client, monkeypatch):
    sent = {}

    async def fake_publish_raw(topic, value):
        sent["topic"], sent["value"] = topic, value

    monkeypatch.setattr(api, "publish_raw", fake_publish_raw)
    # A button widget's topic must be allow-listed for publishing.
    auth_client.post("/api/config", json=_button_config(topic="btn/topic", value="ON"))
    resp = auth_client.post("/api/mqtt/publish", json={"topic": "btn/topic", "value": "ON"})
    assert resp.status_code == 200
    assert sent == {"topic": "btn/topic", "value": "ON"}


# --------------------------------------------------------------------------- #
# POST /api/entity/{id}/command
# --------------------------------------------------------------------------- #
def test_command_requires_auth(client):
    assert client.post(
        "/api/entity/Lamp/command", json={"state": "ON"}
    ).status_code == 401


def test_command_missing_field_400(auth_client):
    # No state, no field -> field validation fails
    assert auth_client.post(
        "/api/entity/Lamp/command", json={"value": 5}
    ).status_code == 400


def test_command_empty_field_400(auth_client):
    assert auth_client.post(
        "/api/entity/Lamp/command", json={"field": "", "value": 5}
    ).status_code == 400


def test_command_string_value_400(auth_client):
    assert auth_client.post(
        "/api/entity/Lamp/command", json={"field": "brightness", "value": "5"}
    ).status_code == 400


def test_command_optimistic_merge_keeps_existing_fields(auth_client, monkeypatch):
    async def fake_publish_value(entity, field, value):
        pass

    monkeypatch.setattr(api, "publish_value", fake_publish_value)
    device_states["Lamp"] = {"state": "ON"}
    resp = auth_client.post(
        "/api/entity/Lamp/command", json={"field": "brightness", "value": 50}
    )
    assert resp.status_code == 200
    # Merge must not clobber pre-existing state
    assert device_states["Lamp"] == {"state": "ON", "brightness": 50}


# --------------------------------------------------------------------------- #
# POST /api/login
# --------------------------------------------------------------------------- #
def test_login_non_dict_body_401(client):
    # A JSON list body -> 401, not 500
    assert client.post("/api/login", json=[1, 2, 3]).status_code == 401


def test_login_non_string_password_401(client):
    assert client.post("/api/login", json={"password": 123}).status_code == 401


def test_login_correct_then_session_true(client):
    assert client.post("/api/login", json={"password": TEST_PASSWORD}).status_code == 200
    assert client.get("/api/session").json() == {"auth": True}
