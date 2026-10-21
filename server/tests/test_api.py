import base64
import logging

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


def _toggle_config(read_topic="tog/state", write_topic="tog/set", on_value="ON", off_value="OFF"):
    """Minimal config with one toggle widget so its read/write topics are configured."""
    return {
        "id": "x",
        "name": "Plan",
        "imageBase64": "",
        "entities": [
            {
                "type": "toggle",
                "toggleConfig": {
                    "readTopic": read_topic,
                    "writeTopic": write_topic,
                    "onValue": on_value,
                    "offValue": off_value,
                },
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


def test_bootstrap_unauthenticated(client):
    resp = client.get("/api/bootstrap")
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth"] is False
    assert "title" in body
    # No private payload leaks to an unauthenticated caller.
    assert "config" not in body
    assert "states" not in body
    assert "topics" not in body


def test_bootstrap_authenticated(auth_client):
    cfg = _number_config()
    assert auth_client.post("/api/config", json=cfg).status_code == 200
    resp = auth_client.get("/api/bootstrap")
    assert resp.status_code == 200
    body = resp.json()
    assert body["auth"] is True
    assert "title" in body
    # Authed payload carries the dynamic data (states + topics) AND a copy of the
    # config. The config is ALSO served separately by /api/config (so a service worker
    # can cache it); including it here keeps the payload a backward-compatible superset
    # so an older cached frontend bundle never breaks on a deploy.
    assert "states" in body and "topics" in body
    assert body["config"] == cfg


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


def test_config_restart_when_toggle_read_topics_changed(auth_client, monkeypatch):
    called = {"n": 0}

    async def fake_restart():
        called["n"] += 1

    monkeypatch.setattr(api, "_restart_mqtt_listener", fake_restart)
    # Seed an initial empty-ish config so the toggle readTopic below is a change.
    auth_client.post("/api/config", json=_number_config(read_topic="sensors/temp"))
    called["n"] = 0
    # Introducing a toggle readTopic must trigger a restart now that
    # subscribed_read_topics includes toggle read topics.
    assert auth_client.post(
        "/api/config", json=_toggle_config(read_topic="tog/state")
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


def test_mqtt_publish_toggle_write_topic_allowed(auth_client, monkeypatch):
    sent = {}

    async def fake_publish_raw(topic, value):
        sent["topic"], sent["value"] = topic, value

    monkeypatch.setattr(api, "publish_raw", fake_publish_raw)
    # A toggle widget's write topic must be allow-listed for publishing.
    auth_client.post("/api/config", json=_toggle_config(write_topic="tog/set", on_value="ON"))
    resp = auth_client.post("/api/mqtt/publish", json={"topic": "tog/set", "value": "ON"})
    assert resp.status_code == 200
    assert sent == {"topic": "tog/set", "value": "ON"}


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


# --------------------------------------------------------------------------- #
# GET /api/camera
# --------------------------------------------------------------------------- #
def test_camera_requires_auth(client):
    assert client.get("/api/camera", params={"url": "http://cam/image.jpg"}).status_code == 401


def test_camera_proxies_image(auth_client, monkeypatch):
    fetched = {}

    def fake_fetch(url):
        fetched["url"] = url
        return b"\xff\xd8jpegdata", "image/jpeg"

    monkeypatch.setattr(api, "_fetch_camera", fake_fetch)
    resp = auth_client.get("/api/camera", params={"url": "http://cam/image.jpg?a=1&b=2"})
    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8jpegdata"
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["cache-control"] == "no-store"
    # The full (decoded) camera URL, including its own query string, reaches the fetcher
    assert fetched["url"] == "http://cam/image.jpg?a=1&b=2"


def test_camera_fetch_error_502(auth_client, monkeypatch):
    def fake_fetch(url):
        raise OSError("camera unreachable")

    monkeypatch.setattr(api, "_fetch_camera", fake_fetch)
    resp = auth_client.get("/api/camera", params={"url": "http://cam/image.jpg"})
    assert resp.status_code == 502


def test_camera_fetch_sends_url_credentials_as_basic_auth(monkeypatch):
    seen = {}

    class FakeResp:
        headers = {"Content-Type": "image/jpeg"}

        def read(self):
            return b"jpg"

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["auth"] = req.get_header("Authorization")
        return FakeResp()

    monkeypatch.setattr(api.urllib.request, "urlopen", fake_urlopen)
    assert api._fetch_camera("http://admin:p%40ss@10.0.0.5:8080/image.jpg") == (b"jpg", "image/jpeg")
    # Credentials leave the URL and travel as a Basic auth header (percent-decoded)
    assert seen["url"] == "http://10.0.0.5:8080/image.jpg"
    assert seen["auth"] == "Basic " + base64.b64encode(b"admin:p@ss").decode()


def test_camera_url_redacted_in_access_log():
    # Same shape as uvicorn's access record: (client, method, path+query, http_version, status)
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/api/camera?url=http%3A%2F%2Fadmin%3Asecret%40cam%2Fimage.jpg&t=1", "1.1", 200),
        None,
    )
    assert all(f.filter(record) for f in logging.getLogger("uvicorn.access").filters)
    msg = record.getMessage()
    assert "secret" not in msg
    assert '"GET /api/camera?<redacted> HTTP/1.1" 200' in msg


# --------------------------------------------------------------------------- #
# /api/camera/power
# --------------------------------------------------------------------------- #
def _camera_config(*cameras):
    """Config with camera widgets, each given as (widget id, cameraConfig)."""
    return {
        "id": "x",
        "name": "Plan",
        "imageBase64": "",
        "entities": [{"id": wid, "type": "camera", "cameraConfig": cfg} for wid, cfg in cameras],
    }


def test_camera_power_requires_auth(client):
    assert client.get("/api/camera/power").status_code == 401
    assert client.post("/api/camera/cam/power", json={"on": False}).status_code == 401


def test_camera_power_unknown_widget_404(auth_client):
    assert auth_client.post("/api/camera/nope/power", json={"on": False}).status_code == 404
    # A widget saved before the request URLs existed has no onUrl -> 404 as well
    auth_client.post("/api/config", json=_camera_config(("cam", {"url": "http://cam/image.jpg"})))
    assert auth_client.post("/api/camera/cam/power", json={"on": True}).status_code == 404


def test_camera_power_request_failure_502(auth_client, monkeypatch):
    requested = []

    def fake_fetch(url, timeout=api.CAMERA_TIMEOUT):
        requested.append(url)
        raise OSError("camera unreachable")

    monkeypatch.setattr(api, "_fetch_camera", fake_fetch)
    auth_client.post("/api/config", json=_camera_config(
        ("cam", {"url": "", "offUrl": "http://cam/off", "onUrl": "http://cam/on"})))
    assert auth_client.post("/api/camera/cam/power", json={"on": False}).status_code == 502
    # The request goes to the widget's own offUrl from the saved config
    assert requested == ["http://cam/off"]


def test_camera_power_state_map(auth_client, monkeypatch):
    answers = {
        "http://a/state": b'{"off_until": 1700000000}',
        "http://b/state": b'{"off_until": null}',
    }

    def fake_fetch(url, timeout=api.CAMERA_TIMEOUT):
        if url not in answers:
            raise OSError("camera unreachable")
        return answers[url], "application/json"

    monkeypatch.setattr(api, "_fetch_camera", fake_fetch)
    auth_client.post("/api/config", json=_camera_config(
        ("off", {"url": "", "statusUrl": "http://a/state"}),
        ("on", {"url": "", "statusUrl": "http://b/state"}),
        ("down", {"url": "", "statusUrl": "http://c/state"}),
        ("bare", {"url": ""}),
    ))
    # Only the camera that reports off is in the map; the unreachable one is left out
    assert auth_client.get("/api/camera/power").json() == {"off": 1700000000}


def test_camera_power_switch_returns_until(auth_client, monkeypatch):
    answers = {
        "http://cam/off": b'{"off_until": 1700000000}',
        "http://cam/on": b'{"off_until": null}',
    }
    timeouts = []

    def fake_fetch(url, timeout=api.CAMERA_TIMEOUT):
        timeouts.append(timeout)
        return answers[url], "application/json"

    monkeypatch.setattr(api, "_fetch_camera", fake_fetch)
    auth_client.post("/api/config", json=_camera_config(
        ("cam", {"url": "", "offUrl": "http://cam/off", "onUrl": "http://cam/on"})))
    assert auth_client.post("/api/camera/cam/power", json={"on": False}).json() == {"until": 1700000000}
    assert auth_client.post("/api/camera/cam/power", json={"on": True}).json() == {"until": None}
    # A camera may answer "on" only once its stream is up, so the switch waits longer than a snapshot
    assert timeouts == [api.CAMERA_POWER_TIMEOUT, api.CAMERA_POWER_TIMEOUT]
