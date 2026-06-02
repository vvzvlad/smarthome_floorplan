import asyncio
import json

import pytest

from src import mqtt_client
from src.mqtt_client import (
    apply_device_message,
    apply_topic_value,
    build_command_payload,
    build_value_payload,
    number_read_topics,
    number_write_topics,
    button_topics,
    toggle_read_topics,
    toggle_write_topics,
    subscribed_read_topics,
    publishable_topics,
    _make_client_kwargs,
)


# --------------------------------------------------------------------------- #
# Helpers / fakes
# --------------------------------------------------------------------------- #
class FakeMessage:
    """Minimal stand-in for an aiomqtt message: stringifiable topic + bytes payload."""

    def __init__(self, topic, payload):
        self._topic = topic
        self.payload = payload

    @property
    def topic(self):
        return self._topic


class _AsyncMessageIterator:
    """Async iterator over a scripted list of messages.

    When ``stop_loop`` is True it raises CancelledError after the last message
    to break the outer ``while True`` reconnect loop deterministically.
    """

    def __init__(self, messages, stop_loop):
        self._messages = list(messages)
        self._stop_loop = stop_loop
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i < len(self._messages):
            msg = self._messages[self._i]
            self._i += 1
            return msg
        if self._stop_loop:
            raise asyncio.CancelledError
        raise StopAsyncIteration


class FakeClient:
    """In-memory async-context-manager client modelled after aiomqtt.Client."""

    def __init__(self, messages=None, stop_loop=True):
        self.subscribed = []
        self.published = []
        self._messages = messages or []
        self._stop_loop = stop_loop

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def subscribe(self, topic):
        self.subscribed.append(topic)

    async def publish(self, topic, payload):
        self.published.append((topic, payload))

    @property
    def messages(self):
        return _AsyncMessageIterator(self._messages, self._stop_loop)


# --------------------------------------------------------------------------- #
# UNIT: number_read_topics / number_write_topics
# --------------------------------------------------------------------------- #
def _num(read=None, write=None, with_cfg=True, etype="number"):
    e = {"type": etype}
    if with_cfg:
        cfg = {}
        if read is not None:
            cfg["readTopic"] = read
        if write is not None:
            cfg["writeTopic"] = write
        e["numberConfig"] = cfg
    else:
        e["numberConfig"] = None
    return e


@pytest.mark.parametrize(
    "config, expected",
    [
        # happy path
        ({"entities": [_num(read="r/1")]}, {"r/1"}),
        # entities key missing entirely
        ({}, set()),
        # entities None
        ({"entities": None}, set()),
        # entities empty
        ({"entities": []}, set()),
        # numberConfig is None
        ({"entities": [_num(with_cfg=False)]}, set()),
        # readTopic missing
        ({"entities": [_num(read=None)]}, set()),
        # readTopic empty string
        ({"entities": [_num(read="")]}, set()),
        # readTopic whitespace only
        ({"entities": [_num(read="   ")]}, set()),
        # readTopic non-string dropped
        ({"entities": [_num(read=123)]}, set()),
        # non-number entity type ignored
        ({"entities": [{"type": "light", "numberConfig": {"readTopic": "x"}}]}, set()),
        # dedup of identical topics
        ({"entities": [_num(read="r/1"), _num(read="r/1")]}, {"r/1"}),
        # multiple distinct
        ({"entities": [_num(read="r/1"), _num(read="r/2")]}, {"r/1", "r/2"}),
    ],
)
def test_number_read_topics(config, expected):
    assert number_read_topics(config) == expected


@pytest.mark.parametrize(
    "config, expected",
    [
        ({"entities": [_num(write="w/1")]}, {"w/1"}),
        ({}, set()),
        ({"entities": None}, set()),
        ({"entities": []}, set()),
        ({"entities": [_num(with_cfg=False)]}, set()),
        ({"entities": [_num(write=None)]}, set()),
        ({"entities": [_num(write="")]}, set()),
        ({"entities": [_num(write="   ")]}, set()),
        ({"entities": [_num(write=123)]}, set()),
        ({"entities": [{"type": "light", "numberConfig": {"writeTopic": "x"}}]}, set()),
        ({"entities": [_num(write="w/1"), _num(write="w/1")]}, {"w/1"}),
        ({"entities": [_num(write="w/1"), _num(write="w/2")]}, {"w/1", "w/2"}),
    ],
)
def test_number_write_topics(config, expected):
    assert number_write_topics(config) == expected


# --------------------------------------------------------------------------- #
# UNIT: button_topics
# --------------------------------------------------------------------------- #
def _btn(topic=None, with_cfg=True):
    e = {"type": "button"}
    if with_cfg:
        cfg = {}
        if topic is not None:
            cfg["topic"] = topic
        e["buttonConfig"] = cfg
    else:
        e["buttonConfig"] = None
    return e


@pytest.mark.parametrize(
    "config, expected",
    [
        # happy path
        ({"entities": [_btn(topic="b/1")]}, {"b/1"}),
        # entities key missing entirely
        ({}, set()),
        # entities None
        ({"entities": None}, set()),
        # entities empty
        ({"entities": []}, set()),
        # buttonConfig is None
        ({"entities": [_btn(with_cfg=False)]}, set()),
        # topic missing
        ({"entities": [_btn(topic=None)]}, set()),
        # topic empty string
        ({"entities": [_btn(topic="")]}, set()),
        # topic whitespace only
        ({"entities": [_btn(topic="   ")]}, set()),
        # topic non-string dropped
        ({"entities": [_btn(topic=123)]}, set()),
        # non-button entity type ignored
        ({"entities": [{"type": "light", "buttonConfig": {"topic": "x"}}]}, set()),
        # dedup of identical topics
        ({"entities": [_btn(topic="b/1"), _btn(topic="b/1")]}, {"b/1"}),
        # multiple distinct
        ({"entities": [_btn(topic="b/1"), _btn(topic="b/2")]}, {"b/1", "b/2"}),
    ],
)
def test_button_topics(config, expected):
    assert button_topics(config) == expected


# --------------------------------------------------------------------------- #
# UNIT: toggle_read_topics / toggle_write_topics
# --------------------------------------------------------------------------- #
def _tog(read=None, write=None, on="ON", off="OFF", with_cfg=True):
    e = {"type": "toggle"}
    if with_cfg:
        cfg = {"onValue": on, "offValue": off}
        if read is not None:
            cfg["readTopic"] = read
        if write is not None:
            cfg["writeTopic"] = write
        e["toggleConfig"] = cfg
    else:
        e["toggleConfig"] = None
    return e


@pytest.mark.parametrize(
    "config, expected",
    [
        # happy path
        ({"entities": [_tog(read="r/1")]}, {"r/1"}),
        # entities key missing entirely
        ({}, set()),
        # entities None
        ({"entities": None}, set()),
        # entities empty
        ({"entities": []}, set()),
        # toggleConfig is None
        ({"entities": [_tog(with_cfg=False)]}, set()),
        # readTopic missing
        ({"entities": [_tog(read=None)]}, set()),
        # readTopic empty string
        ({"entities": [_tog(read="")]}, set()),
        # readTopic whitespace only
        ({"entities": [_tog(read="   ")]}, set()),
        # readTopic non-string dropped
        ({"entities": [_tog(read=123)]}, set()),
        # non-toggle entity type ignored
        ({"entities": [{"type": "light", "toggleConfig": {"readTopic": "x"}}]}, set()),
        # dedup of identical topics
        ({"entities": [_tog(read="r/1"), _tog(read="r/1")]}, {"r/1"}),
        # multiple distinct
        ({"entities": [_tog(read="r/1"), _tog(read="r/2")]}, {"r/1", "r/2"}),
    ],
)
def test_toggle_read_topics(config, expected):
    assert toggle_read_topics(config) == expected


@pytest.mark.parametrize(
    "config, expected",
    [
        ({"entities": [_tog(write="w/1")]}, {"w/1"}),
        ({}, set()),
        ({"entities": None}, set()),
        ({"entities": []}, set()),
        ({"entities": [_tog(with_cfg=False)]}, set()),
        ({"entities": [_tog(write=None)]}, set()),
        ({"entities": [_tog(write="")]}, set()),
        ({"entities": [_tog(write="   ")]}, set()),
        ({"entities": [_tog(write=123)]}, set()),
        ({"entities": [{"type": "light", "toggleConfig": {"writeTopic": "x"}}]}, set()),
        ({"entities": [_tog(write="w/1"), _tog(write="w/1")]}, {"w/1"}),
        ({"entities": [_tog(write="w/1"), _tog(write="w/2")]}, {"w/1", "w/2"}),
    ],
)
def test_toggle_write_topics(config, expected):
    assert toggle_write_topics(config) == expected


# --------------------------------------------------------------------------- #
# UNIT: subscribed_read_topics / publishable_topics
# --------------------------------------------------------------------------- #
def test_subscribed_read_topics():
    # Unions number read topics and toggle read topics; non-read widgets add nothing.
    config = {
        "entities": [
            _num(read="num/read"),
            _tog(read="tog/read"),
            _num(write="num/write"),   # write-only number contributes nothing
            _btn(topic="btn/topic"),   # button contributes nothing
        ]
    }
    assert subscribed_read_topics(config) == {"num/read", "tog/read"}


def test_publishable_topics():
    # Unions number write topics, button topics, and toggle write topics.
    config = {
        "entities": [
            _num(write="num/write"),
            _btn(topic="btn/topic"),
            _tog(write="tog/write"),
            _num(read="num/read"),     # read-only number contributes nothing
            _tog(read="tog/read"),     # read-only toggle contributes nothing
        ]
    }
    assert publishable_topics(config) == {"num/write", "btn/topic", "tog/write"}


# --------------------------------------------------------------------------- #
# UNIT: _make_client_kwargs
# --------------------------------------------------------------------------- #
def test_make_client_kwargs_no_creds(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "mqtt_host", "broker")
    monkeypatch.setattr(mqtt_client.settings, "mqtt_port", 1883)
    monkeypatch.setattr(mqtt_client.settings, "mqtt_username", None)
    monkeypatch.setattr(mqtt_client.settings, "mqtt_password", None)
    assert _make_client_kwargs() == {"hostname": "broker", "port": 1883}


def test_make_client_kwargs_username_only(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "mqtt_host", "broker")
    monkeypatch.setattr(mqtt_client.settings, "mqtt_port", 1883)
    monkeypatch.setattr(mqtt_client.settings, "mqtt_username", "user")
    monkeypatch.setattr(mqtt_client.settings, "mqtt_password", None)
    kwargs = _make_client_kwargs()
    assert kwargs == {"hostname": "broker", "port": 1883, "username": "user"}


def test_make_client_kwargs_username_and_password(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "mqtt_host", "broker")
    monkeypatch.setattr(mqtt_client.settings, "mqtt_port", 1883)
    monkeypatch.setattr(mqtt_client.settings, "mqtt_username", "user")
    monkeypatch.setattr(mqtt_client.settings, "mqtt_password", "pw")
    kwargs = _make_client_kwargs()
    assert kwargs == {"hostname": "broker", "port": 1883, "username": "user", "password": "pw"}


# --------------------------------------------------------------------------- #
# UNIT: build_command_payload / build_value_payload
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw", ["on", "On", "ON"])
def test_build_command_payload_upper(raw):
    assert build_command_payload(raw) == json.dumps({"state": "ON"})


def test_build_value_payload():
    assert build_value_payload("brightness", 128) == json.dumps({"brightness": 128})


# --------------------------------------------------------------------------- #
# UNIT: apply_device_message
# --------------------------------------------------------------------------- #
def test_apply_device_message_valid_dict_updates_and_returns_state():
    states = {}
    ret = apply_device_message(states, "Lamp", json.dumps({"state": "ON"}).encode())
    assert ret == "ON"
    assert states["Lamp"] == {"state": "ON"}


def test_apply_device_message_same_state_returns_none():
    states = {"Lamp": {"state": "ON"}}
    ret = apply_device_message(states, "Lamp", json.dumps({"state": "ON"}).encode())
    assert ret is None
    assert states["Lamp"] == {"state": "ON"}


def test_apply_device_message_invalid_json_no_mutation():
    states = {"Lamp": {"state": "ON"}}
    ret = apply_device_message(states, "Lamp", b"{ broken json")
    assert ret is None
    assert states == {"Lamp": {"state": "ON"}}


@pytest.mark.parametrize("payload", [json.dumps([1, 2, 3]).encode(), json.dumps(42).encode(), b'"text"'])
def test_apply_device_message_non_dict_ignored(payload):
    states = {"Lamp": {"state": "ON"}}
    ret = apply_device_message(states, "Lamp", payload)
    assert ret is None
    assert states == {"Lamp": {"state": "ON"}}


def test_apply_device_message_full_replace_not_merge():
    # Documents replace-not-merge semantics of the broker listener.
    states = {"Lamp": {"state": "ON", "brightness": 128}}
    ret = apply_device_message(states, "Lamp", json.dumps({"state": "OFF"}).encode())
    assert ret == "OFF"
    assert states["Lamp"] == {"state": "OFF"}  # brightness gone, fully replaced


def test_apply_device_message_no_state_key_returns_none():
    states = {}
    ret = apply_device_message(states, "Sensor", json.dumps({"temperature": 21}).encode())
    assert ret is None
    assert states["Sensor"] == {"temperature": 21}


# --------------------------------------------------------------------------- #
# UNIT: apply_topic_value
# --------------------------------------------------------------------------- #
def test_apply_topic_value_decoded_and_stripped():
    values = {}
    apply_topic_value(values, "r/1", b"  42  ")
    assert values["r/1"] == "42"


def test_apply_topic_value_non_utf8_no_raise():
    values = {}
    apply_topic_value(values, "r/1", b"\xff\xfe rest")
    # errors="replace" -> never raises; value still stored
    assert "r/1" in values
    assert values["r/1"].endswith("rest")


def test_apply_topic_value_decode_error_swallowed():
    # Exercise the defensive except branch: a payload whose .decode() raises
    # must be swallowed (function never raises and stores nothing).
    class BadPayload:
        def decode(self, *args, **kwargs):
            raise ValueError("boom")

    values = {}
    apply_topic_value(values, "r/1", BadPayload())  # must not raise
    assert values == {}


# --------------------------------------------------------------------------- #
# INTEGRATION: mqtt_listener_loop
# --------------------------------------------------------------------------- #
async def test_listener_loop_subscribes_and_updates(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "z2m_base", "zigbee2mqtt")
    monkeypatch.setattr(mqtt_client, "RECONNECT_DELAY", 0)
    monkeypatch.setattr(mqtt_client, "read_config", lambda: {"entities": [_num(read="sensors/temp")]})
    mqtt_client.device_states.clear()
    mqtt_client.topic_values.clear()

    messages = [
        FakeMessage("zigbee2mqtt/Lamp", json.dumps({"state": "ON"}).encode()),
        FakeMessage("sensors/temp", b" 21.5 "),
        # 3-part topic: must be skipped for device_states
        FakeMessage("zigbee2mqtt/bridge/state", json.dumps({"state": "online"}).encode()),
    ]
    fake = FakeClient(messages=messages, stop_loop=True)
    monkeypatch.setattr(mqtt_client, "make_client", lambda: fake)

    with pytest.raises(asyncio.CancelledError):
        await mqtt_client.mqtt_listener_loop()

    # Subscribes to base wildcard and the configured read topic
    assert "zigbee2mqtt/#" in fake.subscribed
    assert "sensors/temp" in fake.subscribed
    # 2-part device topic merged
    assert mqtt_client.device_states["Lamp"] == {"state": "ON"}
    # bridge/state is 3 parts -> not stored as a device
    assert "bridge" not in mqtt_client.device_states
    assert "zigbee2mqtt/bridge/state" not in mqtt_client.device_states
    # read topic value captured (decoded+stripped)
    assert mqtt_client.topic_values["sensors/temp"] == "21.5"


async def test_listener_loop_drops_stale_topic_values(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "z2m_base", "zigbee2mqtt")
    monkeypatch.setattr(mqtt_client, "RECONNECT_DELAY", 0)
    # Config only declares sensors/new; sensors/old is stale
    monkeypatch.setattr(mqtt_client, "read_config", lambda: {"entities": [_num(read="sensors/new")]})
    mqtt_client.device_states.clear()
    mqtt_client.topic_values.clear()
    mqtt_client.topic_values["sensors/old"] = "stale"

    fake = FakeClient(messages=[], stop_loop=True)
    monkeypatch.setattr(mqtt_client, "make_client", lambda: fake)

    with pytest.raises(asyncio.CancelledError):
        await mqtt_client.mqtt_listener_loop()

    # Stale topic dropped on (re)subscribe
    assert "sensors/old" not in mqtt_client.topic_values


async def test_listener_loop_reconnects_then_cancel(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "z2m_base", "zigbee2mqtt")
    monkeypatch.setattr(mqtt_client, "RECONNECT_DELAY", 0)
    monkeypatch.setattr(mqtt_client, "read_config", lambda: {"entities": []})
    mqtt_client.device_states.clear()
    mqtt_client.topic_values.clear()

    calls = {"n": 0}

    class FailingThenCancel:
        async def __aenter__(self):
            calls["n"] += 1
            if calls["n"] == 1:
                # First connection raises -> exercise the reconnect branch
                raise RuntimeError("connection lost")
            return self

        async def __aexit__(self, *exc):
            return False

        async def subscribe(self, topic):
            pass

        @property
        def messages(self):
            return _AsyncMessageIterator([], stop_loop=True)

    monkeypatch.setattr(mqtt_client, "make_client", lambda: FailingThenCancel())

    with pytest.raises(asyncio.CancelledError):
        await mqtt_client.mqtt_listener_loop()

    # Connected twice: failed once (reconnect), succeeded once (then cancelled)
    assert calls["n"] == 2


# --------------------------------------------------------------------------- #
# INTEGRATION: publish_command / publish_value / publish_raw
# --------------------------------------------------------------------------- #
async def test_publish_command_exact_topic_and_payload(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "z2m_base", "zigbee2mqtt")
    fake = FakeClient()
    monkeypatch.setattr(mqtt_client, "make_client", lambda: fake)

    await mqtt_client.publish_command("Lamp", "on")

    assert fake.published == [("zigbee2mqtt/Lamp/set", json.dumps({"state": "ON"}))]


async def test_publish_value_exact_topic_and_payload(monkeypatch):
    monkeypatch.setattr(mqtt_client.settings, "z2m_base", "zigbee2mqtt")
    fake = FakeClient()
    monkeypatch.setattr(mqtt_client, "make_client", lambda: fake)

    await mqtt_client.publish_value("Lamp", "brightness", 200)

    assert fake.published == [("zigbee2mqtt/Lamp/set", json.dumps({"brightness": 200}))]


async def test_publish_raw_no_json(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(mqtt_client, "make_client", lambda: fake)

    await mqtt_client.publish_raw("custom/topic", "42")

    # Raw string forwarded as-is, no JSON wrapping
    assert fake.published == [("custom/topic", "42")]
