# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project Overview

**open-canoe** — open CAN bus analyzer with STM32 hardware probe and native desktop GUI (tkinter/ttk).

```
main.py → canoe/gui/app.py (MainWindow)
  ├── gui/lang.py          (ZH/EN string tables, no i18n framework)
  ├── gui/config.py        (colors, fonts, bitrates, MCU targets)
  ├── gui/device_bar.py    (left: MCU, COM port, connect toggle, flash)
  ├── gui/message_table.py (center: ttk.Treeview, color tags)
  ├── gui/send_panel.py    (right: composer, cycle, presets)
  ├── gui/detail_panel.py  (bottom: raw/decoded signal view)
  ├── gui/log_panel.py     (bottom: colored log)
  ├── gui/waveform_window.py (popup: oscilloscope view)
  ├── core/protocol.py     (CRC16/XMODEM binary frame codec)
  ├── core/transport.py    (serial/USB CDC, auto-detect)
  ├── core/models.py       (CANMessage, BusStatistics)
  └── config/settings.py   (Pydantic YAML loader)

firmware/
  common/protocol.c/h      (shared protocol codec)
  f103/main.c, can_engine.c, usb_cdc.c  (F103C8T6 firmware)
  f407/main.c, can_engine.c             (F407VET6 firmware)
  Makefile.f103, Makefile.f407
```

## Run

```bash
uv run python main.py
```

## Architecture

- **Tkinter/ttk** — native GUI, "vista" theme, card-based layout (white cards on `#e8ecf1` bg)
- **lang.py** — simple EN/ZH dict lookup via `L()["key"]`, no framework overhead
- **Async connect** — `_connect_async()` spawns thread, results via `queue.Queue` polled at 200ms
- **Connect toggle** — single button: "连接" when disconnected, "断开" when connected (green)
- **View menu** — toggles device bar, send panel, detail, log; layout reflows via `_relayout()`
- **Firmware** — per-MCU C code sharing `common/protocol.c`, built with `arm-none-eabi-gcc`
- **Demo mode** — fully functional without hardware

## Editing Rules

- ALL user-facing strings go through `L()` dict; add keys to both ZH and EN tables in `gui/lang.py`
- Colors/fonts → `gui/config.py`, never hardcode
- Protocol frame format in `core/protocol.py` must match `firmware/common/protocol.h`
- Per-chip firmware adaptations use `#ifdef STM32F103xB`/`#ifdef STM32F407xx`
