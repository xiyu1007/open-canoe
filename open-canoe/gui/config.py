"""GUI constants — colors, fonts, layout values."""

from __future__ import annotations
import os

__all__ = [
    "BG", "CARD", "PRIMARY", "SECONDARY", "ACCENT", "SUCCESS", "WARNING", "ERROR",
    "TAG_STD", "TAG_EXT", "TAG_ERR", "TAG_MUTED", "TEXT_BG",
    "FONT_UI", "FONT_TITLE", "FONT_SECTION", "FONT_BODY", "FONT_HINT", "FONT_MONO_9",
    "XPAD", "YPAD", "CARD_PAD", "BITRATES", "MCU_TARGETS",
    "MAX_VISIBLE", "MESSAGE_LIMIT", "HISTORY_DIR_NAME", "APP_DATA_DIR",
    "MAX_HISTORY_FILES",
]

BG = "#e8ecf1"
CARD = "#ffffff"
PRIMARY = "#1e293b"
SECONDARY = "#64748b"
ACCENT = "#3b82f6"
SUCCESS = "#16a34a"
WARNING = "#f59e0b"
ERROR = "#ef4444"
TEXT_BG = "#f8fafc"      # text widget / canvas background

# Message trace tag colors
TAG_STD = "#1e293b"       # standard CAN ID
TAG_EXT = "#3b82f6"       # extended CAN ID
TAG_ERR = "#ef4444"       # error frame
TAG_INFO = "#64748b"      # status info
TAG_MUTED = "#94a3b8"     # muted / inactive

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
FONT_UI = "Microsoft YaHei UI"
FONT_MONO = "Consolas"
FONT_TITLE = (FONT_UI, 15, "bold")
FONT_SECTION = (FONT_UI, 10, "bold")
FONT_BODY = (FONT_UI, 9)
FONT_HINT = (FONT_UI, 8)
FONT_MONO_9 = (FONT_MONO, 9)
FONT_MONO_BOLD = (FONT_MONO, 9, "bold")

# ---------------------------------------------------------------------------
# Spacing
# ---------------------------------------------------------------------------
XPAD = 20
YPAD = 14
CARD_PAD = 14

# ---------------------------------------------------------------------------
# CAN bitrates
# ---------------------------------------------------------------------------
BITRATES = ["100 kbps", "125 kbps", "250 kbps", "500 kbps", "1 Mbps"]

# ---------------------------------------------------------------------------
# MCU targets
# ---------------------------------------------------------------------------
MCU_TARGETS = ["STM32F103C8T6", "STM32F407VET6"]

# ---------------------------------------------------------------------------
# Message table limits
# ---------------------------------------------------------------------------
MAX_VISIBLE = 20_000       # max tree items before capping
MESSAGE_LIMIT = 2_000       # default max in-memory messages before offload
HISTORY_DIR_NAME = ""  # history CSV goes directly in APP_DATA_DIR (data/)
MAX_HISTORY_FILES = 2  # keep only N most recent history CSV files

# ---------------------------------------------------------------------------
# App data directory — project-local (open-canoe/), not user AppData
# ---------------------------------------------------------------------------
_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DATA_DIR = os.path.join(_APP_DIR, "data")  # data/.lang, data/*.csv
os.makedirs(APP_DATA_DIR, exist_ok=True)
