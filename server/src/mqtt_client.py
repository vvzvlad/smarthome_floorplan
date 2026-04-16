import asyncio
import json
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Глобальный словарь состояний: { friendly_name: { "state": "ON" | "OFF" } }
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
    """Запускается в фоне при старте приложения.
    Подписывается на zigbee2mqtt/# и обновляет device_states."""
    import aiomqtt

    while True:
        try:
            async with aiomqtt.Client(**_make_client_kwargs()) as client:
                logger.info("MQTT connected to %s:%s", MQTT_HOST, MQTT_PORT)
                await client.subscribe(f"{Z2M_BASE}/#")
                async for message in client.messages:
                    topic = str(message.topic)
                    parts = topic.split("/")
                    # Нас интересует только zigbee2mqtt/{friendly_name} (ровно 2 части)
                    # Игнорируем bridge/*, /set, /get, /availability и т.д.
                    if len(parts) != 2:
                        continue
                    _, friendly_name = parts
                    try:
                        payload = json.loads(message.payload)
                        if isinstance(payload, dict) and "state" in payload:
                            device_states[friendly_name] = {"state": payload["state"]}
                    except (json.JSONDecodeError, Exception):
                        pass
        except Exception as e:
            logger.warning("MQTT connection lost: %s. Reconnecting in 5s...", e)
            await asyncio.sleep(5)


async def publish_command(friendly_name: str, state: str) -> None:
    """Публикует команду в топик zigbee2mqtt/{friendly_name}/set."""
    import aiomqtt

    topic = f"{Z2M_BASE}/{friendly_name}/set"
    payload = json.dumps({"state": state.upper()})
    async with aiomqtt.Client(**_make_client_kwargs()) as client:
        await client.publish(topic, payload)
    logger.info("MQTT publish: %s -> %s", topic, payload)
