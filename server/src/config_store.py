import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/data/config.json"))


def read_config() -> dict:
    """Read config from disk. Returns empty config if file does not exist."""
    if not CONFIG_PATH.exists():
        return {"id": "", "name": "New Floorplan", "imageBase64": "", "entities": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_config(config: dict) -> None:
    """Save config to disk. Creates parent directories if needed."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
