import asyncio
import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Global state dict: { friendly_name: { "state": "ON" | "OFF" } }
device_states: Dict[str, Dict[str, Any]] = {}

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME") or None
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD") or None
Z2M_BASE = "zigbee2mqtt"


def _make_client_kwargs() -> dict:
    kwargs: dict = {"hostname": MQTT_HOST, "port": MQTT_PORT}
    if MQTT_USERNAME:
        kwargs["username"] = MQTT_USERNAME
    if MQTT_PASSWORD:
        kwargs["password"] = MQTT_PASSWORD
    return kwargs


async def mqtt_listener_loop():
    """Background task. Subscribes to zigbee2mqtt/# and updates device_states.
    Only processes messages with exactly 2 topic parts: zigbee2mqtt/{friendly_name}.
    Reconnects automatically on connection loss."""
    import aiomqtt

    while True:
        try:
            async with aiomqtt.Client(**_make_client_kwargs()) as client:
                logger.info("MQTT connected to %s:%s", MQTT_HOST, MQTT_PORT)
                await client.subscribe(f"{Z2M_BASE}/#")
                logger.info("MQTT subscribed to %s/#", Z2M_BASE)
                async for message in client.messages:
                    topic = str(message.topic)
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
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug("Failed to parse MQTT message on %s: %s", topic, e)
        except Exception as e:
            logger.warning("MQTT connection lost: %s. Reconnecting in 5s...", e)
            await asyncio.sleep(5)


async def publish_command(friendly_name: str, state: str) -> None:
    """Publish a command to zigbee2mqtt/{friendly_name}/set."""
    import aiomqtt

    topic = f"{Z2M_BASE}/{friendly_name}/set"
    payload = json.dumps({"state": state.upper()})
    logger.info("Publishing command: [%s] -> %s", friendly_name, state.upper())
    async with aiomqtt.Client(**_make_client_kwargs()) as client:
        await client.publish(topic, payload)
    logger.info("Command published: %s -> %s", topic, payload)
