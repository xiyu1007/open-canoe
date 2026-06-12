# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**open-canoe** — open CAN bus analyzer with STM32 hardware probe and native desktop GUI (tkinter/ttk).

Two components communicate via a binary protocol over USART/USB-CDC:
- **App**: `open-canoe/` — Python desktop GUI
- **Firmware**: `firmware/` — C/STM32 HAL hardware probe

The authoritative development specification is [SPECIFICATION.md](SPECIFICATION.md). Read it first.

## Quick Reference

```
open-canoe/
  main.py → canoe/gui/app.py (MainWindow)
    ├── gui/lang.py          (ZH/EN string tables)
    ├── gui/config.py        (colors, fonts, bitrates, MCU targets)
    ├── gui/device_bar.py    (left: MCU, COM port, connect toggle, flash)
    ├── gui/message_table.py (center: ttk.Treeview, color tags)
    ├── gui/send_panel.py    (right: composer, cycle, presets)
    ├── gui/detail_panel.py  (bottom: raw/decoded signal view)
    ├── gui/log_panel.py     (bottom: colored log)
    ├── gui/waveform_window.py (popup: oscilloscope view)
    ├── core/protocol.py     (binary frame codec — MUST match firmware/inc/protocol.h)
    ├── core/transport.py    (serial/USB CDC, auto-detect)
    ├── core/models.py       (CANMessage, BusStatistics)
    └── config/settings.py   (Pydantic YAML loader)

firmware/
  inc/                       (hardware-independent API headers)
    ├── protocol.h           (wire format — CANONICAL, must match core/protocol.py)
    ├── can_api.h, adc_api.h, comm_api.h, device_api.h, device_config.h
  src/                       (shared driver implementations)
    ├── main.c, protocol_handler.c
    ├── can_driver.c, adc_driver.c, comm_driver.c, device_manager.c
    └── sysmem.c, syscalls.c   ← from CubeMX, DO NOT MODIFY
  f103/                      (STM32F103C8T6: config + HAL + CMSIS)
  f407/                      (STM32F407VET6: config + HAL + CMSIS)
  Makefile_f103, Makefile_f407

tools/
  build.py                   (unified build/flash, JSON output)
  send_cmd.py                (single protocol command)
  test_pyserial.py           (full protocol test suite)

test/
  test_protocol.py           (protocol codec unit tests, no hardware needed)
  test_hardware.py           (full hardware integration test suite)
```

## Run App

```bash
cd open-canoe
uv run python main.py
```

## Build Firmware

```bash
cd tools
python build.py list              # List targets (JSON)
python build.py build f103        # Build STM32F103C8T6
python build.py flash f103        # Build + flash via ST-Link
python build.py clean f103        # Clean

# Manual
cd ../firmware
make -f Makefile_f103
```

## Test

```bash
# Protocol unit tests (no hardware needed)
cd open-canoe && uv run python ../test/test_protocol.py

# Hardware tests (requires flashed probe)
uv run python ../test/test_hardware.py COM7 --loopback
uv run python ../test/test_hardware.py COM7
uv run python ../test/test_hardware.py --scan
```

## Architecture

- **Tkinter/ttk** — native GUI, "vista" theme, card-based layout (white cards on `bg` #e8ecf1)
- **lang.py** — simple EN/ZH dict lookup via `L()["key"]`, no framework overhead
- **Async connect** — `_connect_async()` spawns thread, results via `queue.Queue` polled at 200ms
- **Connect toggle** — single button toggles connect/disconnect with colored dot indicator
- **View menu** — toggles device bar, send panel, detail, log; layout reflows via `_relayout()`
- **Demo mode** — fully functional without hardware

### Communication Protocol

Binary framed protocol. Canonical definition in [SPECIFICATION.md](SPECIFICATION.md) §3.

```
Frame: Magic(0xA5) + Length(LE16) + Cmd(1B) + Seq(LE16) + Data(0..256B) + CRC16(LE16) + EndMagic(0x5A)
CRC:   CRC-CCITT, polynomial 0x1021, initial value 0xFFFF
```

### Firmware Layer Rules

1. **`inc/`** — hardware-independent interfaces only. No MCU types, registers, or CMSIS.
2. **`src/`** — driver implementations using macros from `f103/stm32f103_config.h` etc. All peripheral access via STM32 HAL.
3. **`f103/`, `f407/` etc.** — per-MCU directory with everything needed for that chip. CubeMX files never modified.
4. **`protocol_handler.c`** — pure C, no HAL includes.

### Startup Flow

1. `HAL_Init()` → `SystemClock_Config()` → SysTick re-init → GPIO → Timer → Comm init (HAL IT mode).
2. CAN and ADC NOT auto-started — wait for App commands.
3. On boot, sends device heartbeat frame + enters main polling loop.

## Adding a New MCU

1. **Create `firmware/<mcu>/`** — copy from CubeMX demo:
   - `startup_xxx.s`, `xxx_FLASH.ld`, `system_xxx.c` (never modify)
   - `CMSIS/` entire directory (never modify)
   - `HAL/Inc/` all files, `HAL/Src/` only used modules (never modify)
2. **Add config files** — `stm32xxx_config.h` + `stm32xxx_hal_conf.h` (use existing as template)
3. **Create `Makefile_xxx`** — copy existing, adjust MCU_DIR, flags, defines
4. **Register in `tools/build.py`** TARGETS dict
5. **No changes** to `src/`, `inc/`, `tools/`, or App code

## Editing Rules

- ALL user-facing strings go through `L()` dict; add keys to both ZH and EN tables in `gui/lang.py`
- Colors/fonts → `gui/config.py`, never hardcode
- Protocol frame format in `core/protocol.py` must match `firmware/inc/protocol.h`
- Per-chip firmware adaptations use `#ifdef STM32F103xB`/`#ifdef STM32F407xx`
- CubeMX-origin files must NOT be modified — verified by `diff -rq`
- C naming: `module_verb` / `module_noun`; structs use `typedef`; each `.c`/`.h` has file header

### Key Build Differences Between MCUs

| Aspect | STM32F103C8T6 | STM32F407VET6 |
|--------|---------------|---------------|
| CPU flag | `-mcpu=cortex-m3` | `-mcpu=cortex-m4` |
| FPU flags | none | `-mfpu=fpv4-sp-d16 -mfloat-abi=hard` |
| STM32 define | `-DSTM32F103xB` | `-DSTM32F407xx` |
| Linker script | `f103/STM32F103XX_FLASH.ld` | `f407/STM32F407XX_FLASH.ld` |
| Startup file | `f103/startup_stm32f103xb.s` | `f407/startup_stm32f407xx.s` |
| Flash / RAM | 64K / 20K | 512K / 128K (+ 64K CCM) |

Linker scripts have `(READONLY)` keywords stripped at build time (via sed) for GCC 10 compatibility.
