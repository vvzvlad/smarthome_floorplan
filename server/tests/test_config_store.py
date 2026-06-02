import json

import pytest

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


def test_read_invalid_json_raises(tmp_path, monkeypatch):
    # Pin the current contract: a corrupt file surfaces a JSONDecodeError.
    path = tmp_path / "c.json"
    path.write_text("{ broken", encoding="utf-8")
    monkeypatch.setattr(config_store.settings, "config_path", str(path))
    with pytest.raises(json.JSONDecodeError):
        read_config()


def test_write_creates_nested_dirs(tmp_path, monkeypatch):
    # Exercises mkdir(parents=True) on a path whose parents do not exist.
    nested = tmp_path / "a" / "b" / "c.json"
    monkeypatch.setattr(config_store.settings, "config_path", str(nested))
    payload = {"id": "n", "name": "Nested", "imageBase64": "", "entities": []}
    write_config(payload)
    assert nested.exists()
    assert read_config() == payload


def test_roundtrip_non_ascii(tmp_path, monkeypatch):
    # ensure_ascii=False must preserve non-ASCII content losslessly.
    path = tmp_path / "c.json"
    monkeypatch.setattr(config_store.settings, "config_path", str(path))
    payload = {"id": "x", "name": "Гостиная", "imageBase64": "", "entities": []}
    write_config(payload)
    # Stored as real UTF-8 (not \uXXXX escapes)
    assert "Гостиная" in path.read_text(encoding="utf-8")
    assert read_config() == payload
