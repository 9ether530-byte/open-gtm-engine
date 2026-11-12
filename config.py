"""Configuration for OpenGTM Engine.

Defaults are intentionally conservative. Caps are enforced in engine.py
at mark-sent time. No external service is called.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_CAPS = {"linkedin": 30, "email": 50, "x": 20}
DEFAULT_CONFIG = {
    "daily_caps": dict(DEFAULT_CAPS),
    "port": 8040,
    "db_filename": "leads.db",
}

_CONFIG_PATH = Path(__file__).parent / "config.json"


def config_path() -> Path:
    env = os.environ.get("OPENGTM_CONFIG_PATH")
    return Path(env) if env else _CONFIG_PATH


def load_config(path: str | Path | None = None) -> dict:
    """Load config.json if present, else defaults. Never raises for a missing file."""
    p = Path(path) if path else config_path()
    cfg = {"daily_caps": dict(DEFAULT_CAPS), "port": 8040, "db_filename": "leads.db"}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return cfg
        if isinstance(data, dict):
            caps = data.get("daily_caps") or {}
            for k in DEFAULT_CAPS:
                if k in caps:
                    try:
                        cfg["daily_caps"][k] = int(caps[k])
                    except (TypeError, ValueError):
                        pass
            if "port" in data:
                try:
                    cfg["port"] = int(data["port"])
                except (TypeError, ValueError):
                    pass
    return cfg


def get_caps(path: str | Path | None = None) -> dict:
    return load_config(path)["daily_caps"]
