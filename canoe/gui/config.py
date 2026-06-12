"""GUI constants — colors, fonts, layout values.

Tailwind-inspired palette, same approach as the text-encoding-tool reference.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Palette (Tailwind-inspired)
# ---------------------------------------------------------------------------
BG = "#e8ecf1"           # slate-100 — window background
CARD = "#ffffff"          # white — card background
PRIMARY = "#1e293b"       # slate-800 — body text
SECONDARY = "#64748b"     # slate-500 — hint / secondary text
ACCENT = "#3b82f6"        # blue-500 — buttons, progress, links
ACCENT_HOVER = "#2563eb"  # blue-600 — button hover
SUCCESS = "#16a34a"       # green-600 — ok
WARNING = "#f59e0b"       # amber-500 — warning
ERROR = "#ef4444"         # red-500 — error

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
