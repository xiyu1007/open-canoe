"""GUI constants + simple config loader (replaces settings.py)."""

from __future__ import annotations
import os

__all__ = [
    "BG", "CARD", "PRIMARY", "SECONDARY", "ACCENT", "SUCCESS", "WARNING", "ERROR",
    "TAG_STD", "TAG_EXT", "TAG_ERR", "TAG_MUTED", "TEXT_BG",
    "FONT_UI", "FONT_TITLE", "FONT_SECTION", "FONT_BODY", "FONT_HINT", "FONT_MONO_9",
    "XPAD", "YPAD", "CARD_PAD", "BITRATES", "MCU_TARGETS",
    "MAX_VISIBLE", "APP_DATA_DIR", "load_config",
]

# Colors
BG       = "#e8ecf1"
CARD     = "#ffffff"
PRIMARY  = "#1e293b"
SECONDARY = "#64748b"
ACCENT   = "#3b82f6"
SUCCESS  = "#16a34a"
WARNING  = "#f59e0b"
ERROR    = "#ef4444"
TEXT_BG  = "#f8fafc"

TAG_STD   = "#1e293b"
TAG_EXT   = "#3b82f6"
TAG_ERR   = "#ef4444"
TAG_MUTED = "#94a3b8"

# Fonts
FONT_UI   = "Microsoft YaHei UI"
FONT_MONO = "Consolas"
FONT_TITLE   = (FONT_UI, 15, "bold")
FONT_SECTION = (FONT_UI, 10, "bold")
FONT_BODY    = (FONT_UI, 9)
FONT_HINT    = (FONT_UI, 8)
FONT_MONO_9  = (FONT_MONO, 9)

# Spacing
XPAD     = 20
YPAD     = 14
CARD_PAD = 14

# CAN bitrates
BITRATES = ["100 kbps", "125 kbps", "250 kbps", "500 kbps", "1 Mbps"]

# MCU targets
MCU_TARGETS = ["STM32F103C8T6", "STM32F407VET6"]

# Message table
MAX_VISIBLE = 20_000

# App data directory
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DATA_DIR = os.path.join(_APP_DIR, "data")
os.makedirs(APP_DATA_DIR, exist_ok=True)

_CONFIG_DIR = os.path.join(_APP_DIR, "config")
_DEFAULTS_PATH = os.path.join(_CONFIG_DIR, "defaults.yaml")
_config_cache: dict | None = None


def load_config() -> dict:
    """Load defaults.yaml as a plain dict. Lightweight replacement for settings.py."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        import yaml
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as fh:
            _config_cache = yaml.safe_load(fh) or {}
    except Exception:
        _config_cache = {}
    return _config_cache
