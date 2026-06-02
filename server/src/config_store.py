import json
import os
import shutil
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
    """Save config to disk atomically, keeping a one-generation backup.

    Writes to a temp file in the same directory and os.replace()s it into place so
    a crash mid-write can never leave a truncated/corrupt config. Before replacing,
    the previous config is copied to ``<name>.bak`` so an accidental overwrite (e.g.
    an empty config written by the client) stays recoverable.
    """
    path = Path(settings.config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Back up the previous config (best-effort; never fail a save because of backup).
    if path.exists():
        try:
            shutil.copy2(path, path.parent / (path.name + ".bak"))
        except OSError:
            pass
    tmp = path.parent / (path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
