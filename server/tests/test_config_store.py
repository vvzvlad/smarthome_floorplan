from src import config_store
from src.config_store import read_config, write_config


def test_read_returns_default_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store.settings, "config_path", str(tmp_path / "c.json"))
    cfg = read_config()
    assert cfg == {"id": "", "name": "New Floorplan", "imageBase64": "", "entities": []}


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store.settings, "config_path", str(tmp_path / "c.json"))
    payload = {"id": "x", "name": "My Plan", "imageBase64": "", "entities": [1, 2]}
    write_config(payload)
    assert read_config() == payload
