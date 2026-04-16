import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "/data/config.json"))


def read_config() -> dict:
    """Читает конфиг с диска. Если файла нет — возвращает пустой конфиг."""
    if not CONFIG_PATH.exists():
        return {"id": "", "name": "New Floorplan", "imageBase64": "", "entities": []}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_config(config: dict) -> None:
    """Сохраняет конфиг на диск, создаёт директорию если нужно."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
