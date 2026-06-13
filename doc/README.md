# Open-Canoe / 开放独木舟

**EN** · Open CAN bus analyzer — STM32 hardware probe + native desktop GUI.  
**CN** · 开源 CAN 总线分析仪 — STM32 硬件探针 + 原生桌面应用。

---

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>
## English

### Overview

Open-Canoe is an enterprise-grade CAN bus analysis tool that replaces proprietary solutions like ZCANPRO. It consists of two components:

| Component | Technology | Location |
|-----------|-----------|----------|
| Desktop App | Python 3.11+ / tkinter | `open-canoe/` |
| Hardware Probe Firmware | C / STM32 HAL | `firmware/` |

The two communicate via USART or USB-CDC using a custom binary protocol. The architecture enforces strict separation — the App never depends on firmware internals, and new MCU support requires zero App changes.

### Features

**App (Desktop GUI)**
- Real-time CAN message trace with color-coded table (standard/extended/error)
- Message composer: standard/extended frames, remote frames (RTR), error frames
- Cycle scheduler with configurable interval
- CAN ID filtering (message filter + display filter, independent levels)
- TX/RX toggle with radio-button behavior
- Message collapse by ID (deduplication)
- Auto-increment data on cycle send
- Silent mode (listen-only) with send-button lockout
- Loopback mode (self-test) — no external CAN bus needed for testing
- Signal detail panel with raw hex + uint8/16/32 LE/BE decode
- Waveform probe popup window (requires ADC-capable hardware)
- Colored log panel (info/warn/error)
- Bilingual ZH/EN — instant switch via menu
- Resizable panels via PanedWindow with layout reflow
- Demo mode — fully functional without hardware

**Firmware (Hardware Probe)**
- CAN bus monitoring with microsecond-precision timestamps
- CAN frame transmission (standard/extended/remote)
- CAN error detection & reporting (CRC, stuff, form, ACK, bus-off)
- Optional ADC waveform acquisition (DMA, continuous mode)
- Dual physical interface: USART + USB-CDC
- Hardware abstraction layer — add new MCU without touching core code
- Capability query mechanism (ADC, multi-CAN, USB CDC)
- Boot heartbeat for automatic device identification

### Supported Hardware

| MCU | Core | Flash | CAN | ADC | USB CDC | Firmware |
|-----|------|-------|-----|-----|---------|----------|
| STM32F103C8T6 | Cortex-M3 | 64 KB | 1 ch | Yes | No | `firmware/f103/` |
| STM32F407VET6 | Cortex-M4 | 512 KB | 2 ch | Yes | Yes | `firmware/f407/` |

### Quick Start

```bash
# Clone
git clone <repo-url> canoe && cd canoe

# Run the desktop app (no install required)
cd open-canoe
uv run python main.py
```

The app starts in demo mode — all features work without hardware.

### Build Firmware

```bash
# Prerequisites: arm-none-eabi-gcc (10.3+), GNU Make
cd tools

# Build + flash via ST-Link (recommended)
python build.py flash f103       # STM32F103C8T6
python build.py flash f407       # STM32F407VET6

# Build only
python build.py build f103

# List supported targets (JSON)
python build.py list

# Manual build
cd ../firmware
make -f Makefile_f103
```

### Test Firmware

```bash
uv venv && uv pip install pyserial

# Full protocol test
.venv/Scripts/python tools/test_pyserial.py COM7

# Single command
.venv/Scripts/python tools/send_cmd.py COM7 info
.venv/Scripts/python tools/send_cmd.py COM7 caps
```

### Project Structure

```
canoe/
├── CLAUDE.md                     # AI assistant guidance (at project root)
├── doc/                          # Documentation
│   ├── SPECIFICATION.md          # Canonical development specification (read first!)
│   ├── README.md                 # This file
│   └── REQUIREMENTS.md           # Test requirements & bug tracker
│
├── open-canoe/                   # Desktop App (Python)
│   ├── main.py                   # Entry point
│   ├── pyproject.toml            # Dependencies
│   ├── settings.yaml             # User config (optional)
│   └── canoe/
│       ├── config/               # Settings loader + defaults
│       ├── core/                 # Protocol codec + serial transport
│       └── gui/                  # UI components (tkinter/ttk)
│
├── firmware/                     # Hardware Probe Firmware (C)
│   ├── inc/                      # Hardware-abstracted API headers
│   ├── src/                      # Shared driver implementations
│   ├── f103/                     # STM32F103C8T6 config + HAL + CMSIS
│   ├── f407/                     # STM32F407VET6 config + HAL + CMSIS
│   ├── Makefile_f103
│   └── Makefile_f407
│
├── test/                         # Test scripts
│   ├── test_protocol.py          # Protocol codec unit tests
│   ├── test_hardware.py          # Full hardware integration test
│   ├── test_gui_full.py          # 27-step CAN flow GUI test
│   ├── test_ui_controls.py       # 33-item UI controls GUI test
│   └── test_app.py               # App simulation test (no GUI)
│
└── tools/                        # Build & deploy utilities
    ├── build.py                  # Unified build/flash tool
    ├── deploy.py                 # One-click deploy (build+flash+test+launch)
    ├── deploy.bat                # Windows batch deploy
    ├── send_cmd.py               # Single protocol command sender
    └── test_pyserial.py          # Full protocol test suite
```

### Communication Protocol

The App and firmware communicate via a binary framed protocol:

```
Frame: Magic(0xA5) + Length(LE16) + Cmd(1B) + Seq(LE16) + Data(0..256B) + CRC16(LE16) + EndMagic(0x5A)
CRC:   CRC-CCITT, polynomial 0x1021, initial 0xFFFF
```

Full specification in [SPECIFICATION.md](SPECIFICATION.md) §3.

### Adding a New MCU

1. Create `firmware/<mcu>/` — copy CubeMX files (startup, linker, CMSIS, HAL)
2. Create `stm32<xxx>_config.h` + `stm32<xxx>_hal_conf.h` (use existing as template)
3. Create `Makefile_<mcu>` (copy existing, adjust flags)
4. Register in `tools/build.py` TARGETS dict
5. **No changes** to `inc/`, `src/`, `tools/`, or App code

### Hardware Wiring (F103 + SN65HVD230)

```
STM32F103       SN65HVD230
PA11 (CAN_RX) → CRXD (pin 4)
PA12 (CAN_TX) → CTXD (pin 1)
GND           → GND
3.3V          → VCC
```

### Development

```bash
# App
cd open-canoe
uv run python main.py

# Protocol unit tests (no hardware needed)
uv run python ../test/test_protocol.py

# Hardware integration tests
uv run python ../test/test_hardware.py COM7          # Full test suite
uv run python ../test/test_hardware.py COM7 --loopback  # Loopback quick test
uv run python ../test/test_hardware.py --scan           # Scan for devices

# GUI integration tests (requires flashed probe on COM7)
uv run python ../test/test_gui_full.py               # 27-step CAN flow test
uv run python ../test/test_ui_controls.py            # 33-item UI controls test

# App simulation test (no GUI)
uv run python ../test/test_app.py COM7
```

### Documentation

- [SPECIFICATION.md](SPECIFICATION.md) — Development specification (protocol, architecture, integration plan)
- [CLAUDE.md](CLAUDE.md) — AI agent guidance

### License

TBD

---

<a name="中文"></a>
## 中文

### 概述

Open-Canoe 是一款企业级 CAN 总线分析工具，可替代 ZCANPRO 等商业方案。由两个组件构成：

| 组件 | 技术 | 位置 |
|------|------|------|
| 桌面应用 | Python 3.11+ / tkinter | `open-canoe/` |
| 硬件探针固件 | C / STM32 HAL | `firmware/` |

二者通过 USART 或 USB-CDC 使用自定义二进制协议通信。架构强制分离 — App 不依赖固件内部实现，新增 MCU 无需修改 App。

### 功能特性

**App（桌面 GUI）**
- 实时 CAN 报文追踪，彩色表格（标准帧/扩展帧/错误帧）
- 报文编辑器：标准帧/扩展帧、远程帧（RTR）、错误帧
- 周期发送，可配置间隔
- CAN ID 过滤（报文过滤 + 显示过滤，两级独立）
- TX/RX 单选切换
- 报文折叠（相同 ID 去重）
- 数据自增发送
- 静默模式（仅监听），发送按钮自动锁定
- 环回模式（自测），无需外部 CAN 总线即可测试
- 信号详情面板，支持原始 hex + uint8/16/32 LE/BE 解码
- 波形探头弹窗（需支持 ADC 的硬件）
- 彩色日志面板（信息/警告/错误）
- 中英文双语，菜单即时切换
- 可拖拽调整的面板布局
- 演示模式 — 无硬件可完整体验

**固件（硬件探针）**
- CAN 总线监听，微秒级时间戳
- CAN 报文发送（标准帧/扩展帧/远程帧）
- CAN 错误检测与上报（CRC、位填充、格式、应答、总线关闭）
- 可选 ADC 波形采集（DMA 连续模式）
- 双物理接口：USART + USB-CDC
- 硬件抽象层 — 新增 MCU 无需修改核心代码
- 能力查询机制（ADC、多路 CAN、USB CDC）
- 启动心跳自动设备识别

### 支持硬件

| MCU | 内核 | Flash | CAN | ADC | USB CDC | 固件 |
|-----|------|-------|-----|-----|---------|------|
| STM32F103C8T6 | Cortex-M3 | 64 KB | 1 路 | 有 | 无 | `firmware/f103/` |
| STM32F407VET6 | Cortex-M4 | 512 KB | 2 路 | 有 | 有 | `firmware/f407/` |

### 快速开始

```bash
# 克隆
git clone <repo-url> canoe && cd canoe

# 运行桌面应用（无需手动安装依赖）
cd open-canoe
uv run python main.py
```

程序以演示模式启动，全部功能可正常使用。

### 编译固件

```bash
# 前置条件：arm-none-eabi-gcc (10.3+)、GNU Make
cd tools

# 编译 + 烧录（推荐）
python build.py flash f103       # STM32F103C8T6
python build.py flash f407       # STM32F407VET6

# 仅编译
python build.py build f103

# 列出目标（JSON）
python build.py list
```

### 测试固件

```bash
uv venv && uv pip install pyserial

# 完整协议测试
.venv/Scripts/python tools/test_pyserial.py COM7

# 单条命令
.venv/Scripts/python tools/send_cmd.py COM7 info
```

### 项目结构

参见 English 版本的目录树。

### 通信协议

```
帧格式: Magic(0xA5) + Length(LE16) + Cmd(1B) + Seq(LE16) + Data(0..256B) + CRC16(LE16) + EndMagic(0x5A)
CRC:    CRC-CCITT, 多项式 0x1021, 初始值 0xFFFF
```

完整规范见 [SPECIFICATION.md](SPECIFICATION.md) §3。

### 新增 MCU

1. 创建 `firmware/<mcu>/` — 复制 CubeMX 文件
2. 创建 `stm32<xxx>_config.h` + `stm32<xxx>_hal_conf.h`
3. 创建 `Makefile_<mcu>`
4. 在 `tools/build.py` 注册
5. **无需修改** `inc/`、`src/`、`tools/` 或 App 代码

### 硬件接线 (F103 + SN65HVD230)

```
STM32F103       SN65HVD230
PA11 (CAN_RX) → CRXD (pin 4)
PA12 (CAN_TX) → CTXD (pin 1)
GND           → GND
3.3V          → VCC
```

### 测试

```bash
cd open-canoe

# 协议单元测试（无需硬件）
uv run python ../test/test_protocol.py

# 硬件集成测试
uv run python ../test/test_hardware.py COM7          # 完整测试
uv run python ../test/test_hardware.py COM7 --loopback  # 环回快速测试
uv run python ../test/test_hardware.py --scan           # 扫描设备

# GUI 集成测试（需要 COM7 上已烧录的探针）
uv run python ../test/test_gui_full.py               # 27 步 CAN 流程测试
uv run python ../test/test_ui_controls.py            # 33 项 UI 控件测试

# App 模拟测试（无需 GUI）
uv run python ../test/test_app.py COM7
```

### 文档

- [SPECIFICATION.md](SPECIFICATION.md) — 开发规范（协议、架构、集成方案）
- [CLAUDE.md](CLAUDE.md) — AI 助手指南

### 许可证

待定
