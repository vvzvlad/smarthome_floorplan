import asyncio
import json
import logging
from typing import Any, Dict

from .settings import settings
from .config_store import read_config

logger = logging.getLogger(__name__)

# Global state dict: { friendly_name: { "state": "ON" | "OFF" } }
device_states: Dict[str, Dict[str, Any]] = {}

# Raw last-known values of configured MQTT read topics: { topic: raw_string }
topic_values: Dict[str, str] = {}


def _make_client_kwargs() -> dict:
    kwargs: dict = {"hostname": settings.mqtt_host, "port": settings.mqtt_port}
    if settings.mqtt_username:
        kwargs["username"] = settings.mqtt_username
    if settings.mqtt_password:
        kwargs["password"] = settings.mqtt_password
    return kwargs


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


async def mqtt_listener_loop():
    """Background task. Subscribes to zigbee2mqtt/# and updates device_states.
    Only processes messages with exactly 2 topic parts: zigbee2mqtt/{friendly_name}.
    Reconnects automatically on connection loss."""
    import aiomqtt

    while True:
        try:
            async with aiomqtt.Client(**_make_client_kwargs()) as client:
                logger.info("MQTT connected to %s:%s", settings.mqtt_host, settings.mqtt_port)
                await client.subscribe(f"{settings.z2m_base}/#")
                logger.info("MQTT subscribed to %s/#", settings.z2m_base)
                read_topics = number_read_topics(read_config())
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
                        try:
                            topic_values[topic] = message.payload.decode(errors="replace").strip()
                        except Exception:
                            pass
                    parts = topic.split("/")
                    # Only handle zigbee2mqtt/{friendly_name} — skip bridge/*, /set, /get, etc.
                    if len(parts) != 2:
                        continue
                    _, friendly_name = parts
                    try:
                        payload = json.loads(message.payload)
                        if isinstance(payload, dict):
                            old_state = device_states.get(friendly_name, {}).get("state")
                            device_states[friendly_name] = payload
                            new_state = payload.get("state")
                            if new_state is not None and old_state != new_state:
                                logger.info(
                                    "State change: [%s] %s -> %s",
                                    friendly_name, old_state if old_state is not None else "unknown", new_state
                                )
                    except Exception as e:
                        logger.debug("Failed to parse MQTT message on %s: %s", topic, e)
        except Exception as e:
            logger.warning("MQTT connection lost: %s. Reconnecting in 5s...", e)
            await asyncio.sleep(5)


async def publish_command(friendly_name: str, state: str) -> None:
    """Publish a command to zigbee2mqtt/{friendly_name}/set."""
    import aiomqtt

    topic = f"{settings.z2m_base}/{friendly_name}/set"
    payload = json.dumps({"state": state.upper()})
    logger.info("Publishing command: [%s] -> %s", friendly_name, state.upper())
    async with aiomqtt.Client(**_make_client_kwargs()) as client:
        await client.publish(topic, payload)
    logger.info("Command published: %s -> %s", topic, payload)


async def publish_value(friendly_name: str, field: str, value) -> None:
    """Publish a numeric property set to zigbee2mqtt/{friendly_name}/set, e.g. {"brightness": 128}."""
    import aiomqtt

    topic = f"{settings.z2m_base}/{friendly_name}/set"
    payload = json.dumps({field: value})
    logger.info("Publishing value: [%s] %s -> %s", friendly_name, field, value)
    async with aiomqtt.Client(**_make_client_kwargs()) as client:
        await client.publish(topic, payload)
    logger.info("Value published: %s -> %s", topic, payload)


async def publish_raw(topic: str, value: str) -> None:
    """Publish a raw value (no JSON) to an arbitrary MQTT topic."""
    import aiomqtt

    logger.info("Publishing raw: [%s] -> %s", topic, value)
    async with aiomqtt.Client(**_make_client_kwargs()) as client:
        await client.publish(topic, value)
    logger.info("Raw published: %s -> %s", topic, value)
