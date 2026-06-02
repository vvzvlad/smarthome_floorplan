import asyncio
import json
import logging
from typing import Any, Dict, Optional

from .settings import settings
from .config_store import read_config

logger = logging.getLogger(__name__)

# Global state dict: { friendly_name: { "state": "ON" | "OFF" } }
device_states: Dict[str, Dict[str, Any]] = {}

# Raw last-known values of configured MQTT read topics: { topic: raw_string }
topic_values: Dict[str, str] = {}

# Delay before reconnecting after a connection loss. Module constant so tests
# can monkeypatch it to 0 instead of waiting.
RECONNECT_DELAY = 5


def _make_client_kwargs() -> dict:
    kwargs: dict = {"hostname": settings.mqtt_host, "port": settings.mqtt_port}
    if settings.mqtt_username:
        kwargs["username"] = settings.mqtt_username
    if settings.mqtt_password:
        kwargs["password"] = settings.mqtt_password
    return kwargs


def make_client():
    """Create a broker client. Indirection point so tests can monkeypatch this
    with a fake async-context-manager client and avoid any real network."""
    import aiomqtt

    return aiomqtt.Client(**_make_client_kwargs())


def build_command_payload(state: str) -> str:
    """Build the JSON body for an on/off command: {"state": "ON"|"OFF"}."""
    return json.dumps({"state": state.upper()})


def build_value_payload(field: str, value) -> str:
    """Build the JSON body for a numeric property set: {<field>: <value>}."""
    return json.dumps({field: value})


def apply_topic_value(values: dict, topic: str, payload_bytes) -> None:
    """Store the decoded+stripped raw value of a read topic. Never raises."""
    try:
        values[topic] = payload_bytes.decode(errors="replace").strip()
    except Exception:
        pass


def apply_device_message(
    states: dict, friendly_name: str, payload_bytes, topic: Optional[str] = None
) -> Optional[str]:
    """Merge a per-device MQTT message into ``states``.

    JSON-parse ``payload_bytes``; if it is a dict, fully replace
    ``states[friendly_name]`` with it (replace, not merge) and return the new
    ``state`` value when it changed (else None). On invalid JSON or a non-dict
    payload, leave ``states`` unchanged and return None. Never raises.

    ``topic`` is used only for the parse-failure debug log; when omitted it
    falls back to ``friendly_name``.
    """
    try:
        payload = json.loads(payload_bytes)
    except Exception as e:
        # Log the full topic (as the original loop did) to keep this strictly
        # behaviour-preserving relative to the pre-refactor message handler.
        logger.debug(
            "Failed to parse MQTT message on %s: %s",
            topic if topic is not None else friendly_name, e
        )
        return None
    if not isinstance(payload, dict):
        return None
    old_state = states.get(friendly_name, {}).get("state")
    states[friendly_name] = payload
    new_state = payload.get("state")
    if new_state is not None and old_state != new_state:
        logger.info(
            "State change: [%s] %s -> %s",
            friendly_name, old_state if old_state is not None else "unknown", new_state
        )
        return new_state
    return None


def number_read_topics(config: dict) -> set:
    """Collect non-empty readTopics of all number widgets in the config."""
    topics = set()
    for e in config.get("entities", []) or []:
        if e.get("type") == "number":
            cfg = e.get("numberConfig") or {}
            rt = cfg.get("readTopic")
            if isinstance(rt, str) and rt.strip():
                topics.add(rt)
    return topics


def number_write_topics(config: dict) -> set:
    """Collect non-empty writeTopics of all number widgets in the config."""
    topics = set()
    for e in config.get("entities", []) or []:
        if e.get("type") == "number":
            cfg = e.get("numberConfig") or {}
            wt = cfg.get("writeTopic")
            if isinstance(wt, str) and wt.strip():
                topics.add(wt)
    return topics


def button_topics(config: dict) -> set:
    """Collect non-empty topics of all button widgets in the config."""
    topics = set()
    for e in config.get("entities", []) or []:
        if e.get("type") == "button":
            cfg = e.get("buttonConfig") or {}
            t = cfg.get("topic")
            if isinstance(t, str) and t.strip():
                topics.add(t)
    return topics


def toggle_read_topics(config: dict) -> set:
    """Collect non-empty readTopics of all toggle widgets in the config."""
    topics = set()
    for e in config.get("entities", []) or []:
        if e.get("type") == "toggle":
            cfg = e.get("toggleConfig") or {}
            rt = cfg.get("readTopic")
            if isinstance(rt, str) and rt.strip():
                topics.add(rt)
    return topics


def toggle_write_topics(config: dict) -> set:
    """Collect non-empty writeTopics of all toggle widgets in the config."""
    topics = set()
    for e in config.get("entities", []) or []:
        if e.get("type") == "toggle":
            cfg = e.get("toggleConfig") or {}
            wt = cfg.get("writeTopic")
            if isinstance(wt, str) and wt.strip():
                topics.add(wt)
    return topics


def subscribed_read_topics(config: dict) -> set:
    """All MQTT read topics the listener must subscribe to (number + toggle widgets)."""
    return number_read_topics(config) | toggle_read_topics(config)


def publishable_topics(config: dict) -> set:
    """All topics the /api/mqtt/publish endpoint may publish to
    (number write topics + button topics + toggle write topics)."""
    return number_write_topics(config) | button_topics(config) | toggle_write_topics(config)


async def mqtt_listener_loop():
    """Background task. Subscribes to zigbee2mqtt/# and updates device_states.
    Only processes messages with exactly 2 topic parts: zigbee2mqtt/{friendly_name}.
    Reconnects automatically on connection loss."""
    while True:
        try:
            async with make_client() as client:
                logger.info("MQTT connected to %s:%s", settings.mqtt_host, settings.mqtt_port)
                await client.subscribe(f"{settings.z2m_base}/#")
                logger.info("MQTT subscribed to %s/#", settings.z2m_base)
                read_topics = subscribed_read_topics(read_config())
                for t in read_topics:
                    await client.subscribe(t)
                if read_topics:
                    logger.info("MQTT subscribed to %d config read topic(s)", len(read_topics))
                # Drop cached values for topics that are no longer configured
                for stale in [k for k in topic_values if k not in read_topics]:
                    topic_values.pop(stale, None)
                async for message in client.messages:
                    topic = str(message.topic)
                    if topic in read_topics:
                        apply_topic_value(topic_values, topic, message.payload)
                    parts = topic.split("/")
                    # Only handle zigbee2mqtt/{friendly_name} — skip bridge/*, /set, /get, etc.
                    if len(parts) != 2:
                        continue
                    _, friendly_name = parts
                    apply_device_message(device_states, friendly_name, message.payload, topic)
        except Exception as e:
            logger.warning("MQTT connection lost: %s. Reconnecting in %ss...", e, RECONNECT_DELAY)
            await asyncio.sleep(RECONNECT_DELAY)


async def publish_command(friendly_name: str, state: str) -> None:
    """Publish a command to zigbee2mqtt/{friendly_name}/set."""
    topic = f"{settings.z2m_base}/{friendly_name}/set"
    payload = build_command_payload(state)
    logger.info("Publishing command: [%s] -> %s", friendly_name, state.upper())
    async with make_client() as client:
        await client.publish(topic, payload)
    logger.info("Command published: %s -> %s", topic, payload)


async def publish_value(friendly_name: str, field: str, value) -> None:
    """Publish a numeric property set to zigbee2mqtt/{friendly_name}/set, e.g. {"brightness": 128}."""
    topic = f"{settings.z2m_base}/{friendly_name}/set"
    payload = build_value_payload(field, value)
    logger.info("Publishing value: [%s] %s -> %s", friendly_name, field, value)
    async with make_client() as client:
        await client.publish(topic, payload)
    logger.info("Value published: %s -> %s", topic, payload)


async def publish_raw(topic: str, value: str) -> None:
    """Publish a raw value (no JSON) to an arbitrary MQTT topic."""
    logger.info("Publishing raw: [%s] -> %s", topic, value)
    async with make_client() as client:
        await client.publish(topic, value)
    logger.info("Raw published: %s -> %s", topic, value)
