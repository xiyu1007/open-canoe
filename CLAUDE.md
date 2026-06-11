# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open-Canoe is an extensible CAN bus analysis tool firmware (hardware driver side). It supports multiple STM32 MCUs through a hardware abstraction layer, communicating with a PC-side App via USART or USB-CDC using a custom binary protocol. App code is not part of this repository.

## Build & Flash

- **Toolchain**: `arm-none-eabi-gcc` (bare-metal ARM GCC, tested with 10.3)
- **Unified build tool** (recommended):
  ```bash
  cd tools
  python build.py list              # List supported targets (JSON)
  python build.py build f103        # Build STM32F103C8T6
  python build.py flash f103        # Build + flash via ST-Link
  python build.py clean f103        # Clean
  ```
- **Manual**: `cd hardware && make -f Makefile_f103`
- **Flash**: `st-flash --reset write build_f103/open_canoe_f103.bin 0x08000000`

### Test

```bash
uv venv && uv pip install pyserial
.venv\Scripts\python tools/test_pyserial.py COM7    # Full test
.venv\Scripts\python tools/send_cmd.py COM7 info    # Single command
```

### Key Build Differences Between MCUs

| Aspect | STM32F103C8T6 | STM32F407VET6 |
|--------|---------------|---------------|
| CPU flag | `-mcpu=cortex-m3` | `-mcpu=cortex-m4` |
| FPU flags | none | `-mfpu=fpv4-sp-d16 -mfloat-abi=hard` |
| STM32 define | `-DSTM32F103xB` | `-DSTM32F407xx` |
| Linker script | `f103/STM32F103XX_FLASH.ld` | `f407/STM32F407XX_FLASH.ld` |
| Startup file | `f103/startup_stm32f103xb.s` | `f407/startup_stm32f407xx.s` |
| Flash / RAM | 64K / 20K | 512K / 128K (+ 64K CCM) |

Note: Linker scripts have `(READONLY)` keywords stripped at build time (via sed) for GCC 10 compatibility.

## Architecture

```
hardware/
├── f103/                       # STM32F103C8T6 — ALL MCU-specific files
│   ├── stm32f103_config.h      ← created by us (pin map, clocks, features)
│   ├── stm32f1xx_hal_conf.h    ← created by us (HAL module selection)
│   ├── startup_stm32f103xb.s   ← from CubeMX, DO NOT MODIFY
│   ├── STM32F103XX_FLASH.ld    ← from CubeMX, DO NOT MODIFY
│   ├── system_stm32f1xx.c      ← from CubeMX, DO NOT MODIFY
│   ├── CMSIS/                  ← from CubeMX, DO NOT MODIFY
│   │   ├── Core/Include/
│   │   └── Device/ST/STM32F1xx/Include/
│   └── HAL/                    ← from CubeMX, DO NOT MODIFY
│       ├── Inc/ (all files)
│       └── Src/ (only used: hal, can, adc, uart, usart, dma, gpio,
│                  gpio_ex, rcc, rcc_ex, cortex, flash, flash_ex,
│                  pwr, exti, tim)
├── f407/                       # STM32F407VET6 — same structure
├── inc/                        # Hardware-abstracted shared headers
├── src/                        # Shared firmware source (all HAL-based)
│   ├── main.c, protocol_handler.c
│   ├── can_driver.c, adc_driver.c, comm_driver.c
│   ├── device_manager.c
│   └── sysmem.c, syscalls.c   ← from CubeMX, DO NOT MODIFY
├── Makefile_f103
└── Makefile_f407

tools/                          # PC-side scripts
├── build.py                    # Unified build/flash (JSON output for App)
├── send_cmd.py                 # Send single protocol command
└── test_pyserial.py            # Full protocol test suite
```

### Layer Rules

1. **`inc/`** — hardware-independent interfaces only. No MCU types, registers, or CMSIS.
2. **`src/`** — driver implementations using macros from `f103/stm32f103_config.h` etc. All peripheral access via STM32 HAL.
3. **`hardware/f103/` etc.** — per-MCU directory with everything needed for that chip. CubeMX files never modified.
4. **`protocol_handler.c`** — pure C, no HAL includes.

### Startup Flow

1. `HAL_Init()` → `SystemClock_Config()` → SysTick re-init → GPIO → Timer → Comm init (HAL IT mode).
2. CAN and ADC NOT auto-started — wait for App commands.
3. On boot, sends device heartbeat frame + enters main polling loop.

## Communication Protocol

Binary framed protocol. See `DESIGN.md` for full spec and `hardware/inc/protocol.h` for C structs.
- Frame: Magic(0xA5) + Length(LE16) + Cmd(1B) + Seq(LE16) + Data + CRC16 + End(0x5A)
- CRC16-CCITT, polynomial 0x1021, initial 0xFFFF

## Adding a New MCU

1. **Create `hardware/xxx/`** — copy from CubeMX demo:
   - `startup_xxx.s`, `xxx_FLASH.ld`, `system_xxx.c` (never modify)
   - `CMSIS/` entire directory (never modify)
   - `HAL/Inc/` all files, `HAL/Src/` only used modules (never modify)
2. **Add config files** — `stm32xxx_config.h` + `stm32xxx_hal_conf.h` (use existing as template)
3. **Create `Makefile_xxx`** — copy existing, adjust MCU_DIR, flags, defines
4. **Register in `tools/build.py`** TARGETS dict
5. **No changes** to `src/`, `inc/`, or `tools/send_cmd.py`

Files from CubeMX must be identical to the demo — verified by `diff -rq`.

## Coding Conventions

- C language, STM32 HAL library
- Naming: `module_verb` / `module_noun`
- Structs use `typedef`, each field documented
- Each `.c`/`.h` has a file header comment
- MCU differences go through `device_config.h` → MCU-specific config macros
