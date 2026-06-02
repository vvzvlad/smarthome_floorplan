import json
from pathlib import Path

from .settings import settings


def read_config() -> dict:
    """Read config from disk. Returns empty config if file does not exist."""
    path = Path(settings.config_path)
    if not path.exists():
        return {"id": "", "name": "New Floorplan", "imageBase64": "", "entities": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_config(config: dict) -> None:
    """Save config to disk. Creates parent directories if needed."""
    path = Path(settings.config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
