"""Typed application configuration loaded from YAML.

Resolution order:
1. <project_root>/settings.yaml
2. %APPDATA%/canoe/settings.yaml
3. canoe/config/defaults.yaml (shipped)
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULTS_PATH = Path(__file__).resolve().parent / "defaults.yaml"


class TransportSettings(BaseModel, frozen=True):
    preferred: str = "usb_cdc"
    serial_baud: int = Field(default=921600, ge=9600, le=12_000_000)
    auto_connect: bool = False
    vid: int = 0x0483
    pid: int = 0x5740


class CANSettings(BaseModel, frozen=True):
    bitrate: int = Field(default=500_000)
    silent_mode: bool = False


class UISettings(BaseModel, frozen=True):
    theme: str = "light"
    max_log_lines: int = Field(default=100_000, ge=1000)
    message_limit: int = Field(default=2_000, ge=200, description="Max in-memory messages before offload")


class Settings(BaseModel, frozen=True):
    transport: TransportSettings = Field(default_factory=TransportSettings)
    can: CANSettings = Field(default_factory=CANSettings)
    ui: UISettings = Field(default_factory=UISettings)


def load_settings(path: Path | None = None) -> Settings:
    defaults = _read_yaml(_DEFAULTS_PATH)
    user: dict = {}
    for src in (_appdata_path(), _project_local_path()):
        if src.exists():
            user = _deep_merge(user, _read_yaml(src))
    if path and path.exists():
        user = _deep_merge(user, _read_yaml(path))
    merged = _deep_merge(defaults, user)
    return Settings.model_validate(merged)


def _project_local_path() -> Path:
    return _PROJECT_ROOT / "settings.yaml"


def _appdata_path() -> Path:
    import os
    import platform

    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "canoe" / "settings.yaml"


def _read_yaml(p: Path) -> dict:
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
