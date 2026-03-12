from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from monitor_core import MonitorConfig, MonitorState


DEFAULT_CONFIG_PATH = Path("config.json")
DEFAULT_STATE_PATH = Path("state.json")


def load_config(path: str | Path | None = None) -> MonitorConfig:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return MonitorConfig()

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    return MonitorConfig(**payload)


def save_config(config: MonitorConfig, path: str | Path | None = None) -> Path:
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    config_path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return config_path


def load_state(path: str | Path | None = None) -> MonitorState:
    state_path = Path(path) if path is not None else DEFAULT_STATE_PATH
    if not state_path.exists():
        return MonitorState()

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    last_buy_at = payload.get("last_buy_at")
    return MonitorState(
        last_buy_at=datetime.fromisoformat(last_buy_at) if last_buy_at else None,
    )


def save_state(state: MonitorState, path: str | Path | None = None) -> Path:
    state_path = Path(path) if path is not None else DEFAULT_STATE_PATH
    payload = {"last_buy_at": state.last_buy_at.isoformat() if state.last_buy_at else None}
    state_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return state_path
