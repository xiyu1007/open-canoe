# Open-Canoe

**EN** · Open CAN bus analyzer — STM32 hardware probe.
**CN** · 开源 CAN 总线分析仪 — STM32 硬件探针。

---

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>

## English

### Features

- Real-time CAN message trace (STD / EXT / RTR / ERR)
- Loopback self-test — no external CAN bus needed
- Cycle scheduler with configurable interval
- CAN ID filtering + message collapse by ID
- History viewer with regex search and export
- Silent mode + signal detail panel + waveform probe
- Bilingual ZH / EN

### Pin Connections

| Supported Device | CAN1 RX | CAN1 TX | USART TX | USART RX |
|-----------------|---------|---------|----------|----------|
| STM32F103C8T6 | PA11 | PA12 | PA9 | PA10 |
| STM32F407VET6 | PB8 | PB9 | PA9 | PA10 |

### Prerequisites

| Tool                                                                                                                      | Required For                 |
| ------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| [uv](https://docs.astral.sh/uv/)                                                                                             | Python dependency management |
| [arm-none-eabi-gcc](https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain) (10.3+) | Firmware compilation         |
| [GNU Make](https://www.msys2.org/)                                                                                           | Firmware build               |
| [ST-Link](https://github.com/stlink-org/stlink) (`st-flash`)                                                               | Firmware flashing            |

### Quick Start

```bash
# Install Python deps & run
cd open-canoe
uv run python main.py

# Build, flash & launch (one command)
uv run python tools/deploy.py
```

### Project Structure

```
├── open-canoe/          # Desktop App (Python + tkinter)
│   ├── config/defaults.yaml   # Single configuration file
│   ├── core/                  # Protocol codec + serial transport
│   └── gui/                   # UI components
├── firmware/            # Hardware Probe Firmware (C)
│   ├── inc/                   # API headers
│   ├── src/                   # Driver implementations
│   └── f103/ f407/            # MCU config + HAL
├── test/                # Test scripts
├── tools/               # deploy.py, clean.py + .bat
└── doc/                 # SPECIFICATION.md, REQUIREMENTS.md
```

### Communication Protocol

```
Magic(0xA5) + Length(LE16) + Cmd(1B) + Seq(LE16) + Data(0..256B) + CRC16(LE16) + EndMagic(0x5A)
CRC: CRC-CCITT, polynomial 0x1021, initial 0xFFFF
```

Full spec: [doc/SPECIFICATION.md](doc/SPECIFICATION.md)

### Documentation

- [doc/SPECIFICATION.md](doc/SPECIFICATION.md) — Development specification
- [doc/REQUIREMENTS.md](doc/REQUIREMENTS.md) — Test requirements & bug tracker
- [CLAUDE.md](CLAUDE.md) — AI agent guidance

---

<a name="中文"></a>

## 中文

### 功能特性

- 实时 CAN 报文追踪（标准 / 扩展 / 远程 / 错误）
- 环回自测 — 无需外部 CAN 总线
- 周期发送，可配置间隔
- CAN ID 过滤 + 报文折叠去重
- 历史查看器：正则搜索 + 导出
- 静默模式 + 信号详情 + 波形探头
- 中英文双语

### 引脚连接

| 支持的设备 | CAN1 RX | CAN1 TX | USART TX | USART RX |
|-----------|---------|---------|----------|----------|
| STM32F103C8T6 | PA11 | PA12 | PA9 | PA10 |
| STM32F407VET6 | PB8 | PB9 | PA9 | PA10 |

### 环境要求

| 工具                                                                                                                      | 用途            |
| ------------------------------------------------------------------------------------------------------------------------- | --------------- |
| [uv](https://docs.astral.sh/uv/)                                                                                             | Python 依赖管理 |
| [arm-none-eabi-gcc](https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain) (10.3+) | 固件编译        |
| [GNU Make](https://www.msys2.org/)                                                                                           | 固件构建        |
| [ST-Link](https://github.com/stlink-org/stlink) (`st-flash`)                                                               | 固件烧录        |

### 快速开始

```bash
# 安装 Python 依赖并运行
cd open-canoe
uv run python main.py

# 编译、烧录并启动（一条命令）
uv run python tools/deploy.py
```

### 项目结构

```
├── open-canoe/          # 桌面 App (Python + tkinter)
│   ├── config/defaults.yaml   # 统一配置文件
│   ├── core/                  # 协议编解码 + 串口传输
│   └── gui/                   # UI 组件
├── firmware/            # 硬件探针固件 (C)
│   ├── inc/                   # API 头文件
│   ├── src/                   # 驱动实现
│   └── f103/ f407/            # MCU 配置 + HAL
├── test/                # 测试脚本
├── tools/               # deploy.py, clean.py + .bat
└── doc/                 # SPECIFICATION.md, REQUIREMENTS.md
```

### 通信协议

```
Magic(0xA5) + Length(LE16) + Cmd(1B) + Seq(LE16) + Data(0..256B) + CRC16(LE16) + EndMagic(0x5A)
CRC: CRC-CCITT, 多项式 0x1021, 初始值 0xFFFF
```

完整规范：[doc/SPECIFICATION.md](doc/SPECIFICATION.md)

### 文档

- [doc/SPECIFICATION.md](doc/SPECIFICATION.md) — 开发规范
- [doc/REQUIREMENTS.md](doc/REQUIREMENTS.md) — 测试需求与 Bug 追踪
- [CLAUDE.md](CLAUDE.md) — AI 助手指南
