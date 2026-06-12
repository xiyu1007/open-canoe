# Canoe — Open CAN Bus Analyzer / 开源 CAN 总线分析仪

**EN** · CAN bus analyzer with STM32 hardware probe and native desktop GUI.

**CN** · 基于 STM32 硬件探测器的 CAN 总线分析仪，原生桌面界面。

---

**EN** | [中文](#中文)

---

## EN

### Features

- **MCU selector** — STM32F103C8T6 / STM32F407VET6 target switching
- **Real-time message trace** — color-coded table (standard=dark, extended=blue, error=red)
- **Message composer** — send standard/extended CAN frames, error frames
- **Cycle scheduler** — periodic send with configurable interval, one-click start/stop
- **OBD-II presets** — RPM, Speed, VIN, Coolant, TPMS quick-send buttons
- **Bitrate configuration** — 100k / 125k / 250k / 500k / 1M bps
- **Silent mode** — listen-only, no ACK
- **Signal detail panel** — raw hex + uint8/16/32 decode on row selection
- **Waveform probe** — separate popup window for CAN bus signal visualization
- **Colored log panel** — timestamped info/error/warning messages, collapsible
- **USB CDC + UART** — auto-detected, graceful fallback
- **Demo mode** — fully functional without hardware

### Quick Start

```bash
# Clone
git clone <repo-url> canoe && cd canoe

# Run (uv auto-resolves dependencies)
uv run python main.py
```

No install required. The app starts in demo mode — send messages, test cycle mode, explore all features without hardware.

### Layout

```
┌──────────────┬──────────────────────────────┬──────────────┐
│  DEVICE BAR  │  MESSAGE TRACE (Treeview)    │  SEND PANEL  │
│  MCU Target  │  No│Time  │ID    │DLC│Data   │  CAN ID      │
│  [Connect]   │  1 │12:.. │0x7DF │8  │02 01..│  Type/DLC    │
│  Bitrate     │  2 │12:.. │0x601 │3  │03 22..│  Data hex    │
│  Waveform    │  ...                          │  [Send Once] │
│  Filters     │                               │  [Cycle]     │
│              ├───────────────────────────────┤  Presets     │
│              │  SIGNAL DETAILS               │              │
│              │  Raw: ID/Type/DLC/Data        │              │
│              │  Decoded: uint8/16/32         │              │
├──────────────┴───────────────────────────────┴──────────────┤
│  LOG / ERRORS (collapsible)                                  │
├──────────────────────────────────────────────────────────────┤
│  ● Connected — COM3 │ RX: 1250 msg/s │ TX: 42 │ Errors: 0   │
└──────────────────────────────────────────────────────────────┘
```

### Hardware

| Component | Recommended |
|-----------|-------------|
| MCU | STM32F103C8T6 (Blue Pill) or STM32F407VET6 |
| CAN Transceiver | SN65HVD230 (3.3V) or TJA1050 |
| Connection | USB (CDC) or USB-TTL (UART) |

#### Wiring (F103 + SN65HVD230)

```
STM32F103     SN65HVD230
PB8 (CAN_RX)  →  CRXD (pin 4)
PB9 (CAN_TX)  →  CTXD (pin 1)
GND           →  GND
3.3V          →  VCC
```

### Configuration

Edit `settings.yaml` in the project root:

```yaml
transport:
  preferred: usb_cdc
  serial_baud: 921600
  auto_connect: false

can:
  bitrate: 500000
  silent_mode: false

ui:
  theme: light
  max_log_lines: 100000
```

### Development

```bash
# Install dev deps
uv pip install -e ".[dev]"

# Lint & format
ruff check canoe/ && ruff format canoe/

# Type check
mypy canoe/

# Run tests
pytest tests/ -v
```

See [CLAUDE.md](CLAUDE.md) for the full architecture guide.

### License

TBD

---

## 中文

### 功能特性

- **MCU 选择器** — 支持 STM32F103C8T6 / STM32F407VET6 切换
- **实时报文追踪** — 彩色表格（标准帧深色、扩展帧蓝色、错误帧红色）
- **报文编辑** — 发送标准帧/扩展帧、错误帧
- **周期发送** — 可配置间隔的定时循环发送，一键启停
- **OBD-II 预设** — 转速、车速、VIN、冷却液、胎压等一键发送
- **波特率配置** — 100k / 125k / 250k / 500k / 1M bps
- **静默模式** — 仅监听，不应答 ACK
- **信号详情面板** — 选中行后显示原始 hex + uint8/16/32 解码
- **波形探头** — 独立弹窗显示 CAN 总线信号波形
- **彩色日志面板** — 带时间戳的 info/error/warning 消息，可折叠
- **USB CDC + UART** — 自动检测，优雅降级
- **演示模式** — 无硬件也可完整体验所有功能

### 快速开始

```bash
# 克隆仓库
git clone <repo-url> canoe && cd canoe

# 运行（uv 自动解析依赖）
uv run python main.py
```

无需手动安装依赖。程序以演示模式启动——可发送报文、测试周期发送、浏览全部功能。

### 布局

```
┌──────────────┬──────────────────────────────┬──────────────┐
│  设备栏       │  报文追踪 (树形表格)           │  发送面板     │
│  MCU 型号    │  No│时间  │ID    │DLC│数据   │  CAN ID      │
│  [连接]      │  1 │12:.. │0x7DF │8  │02 01..│  类型/DLC    │
│  波特率      │  2 │12:.. │0x601 │3  │03 22..│  数据 hex    │
│  波形        │  ...                          │  [单次发送]   │
│  过滤器      │                               │  [周期发送]   │
│              ├───────────────────────────────┤  预设        │
│              │  信号详情                      │              │
│              │  原始: ID/类型/DLC/数据        │              │
│              │  解码: uint8/16/32            │              │
├──────────────┴───────────────────────────────┴──────────────┤
│  日志 / 错误（可折叠）                                        │
├──────────────────────────────────────────────────────────────┤
│  ● 已连接 COM3 │ RX: 1250 msg/s │ TX: 42 │ 错误: 0          │
└──────────────────────────────────────────────────────────────┘
```

### 硬件

| 组件 | 推荐型号 |
|------|---------|
| 主控 MCU | STM32F103C8T6 (Blue Pill) 或 STM32F407VET6 |
| CAN 收发器 | SN65HVD230 (3.3V) 或 TJA1050 |
| 连接方式 | USB (CDC) 或 USB-TTL (UART) |

#### 接线 (F103 + SN65HVD230)

```
STM32F103     SN65HVD230
PB8 (CAN_RX)  →  CRXD (pin 4)
PB9 (CAN_TX)  →  CTXD (pin 1)
GND           →  GND
3.3V          →  VCC
```

### 配置

编辑项目根目录下的 `settings.yaml`：

```yaml
transport:
  preferred: usb_cdc
  serial_baud: 921600
  auto_connect: false

can:
  bitrate: 500000
  silent_mode: false

ui:
  theme: light
  max_log_lines: 100000
```

### 开发

```bash
# 安装开发依赖
uv pip install -e ".[dev]"

# 代码检查 & 格式化
ruff check canoe/ && ruff format canoe/

# 类型检查
mypy canoe/

# 运行测试
pytest tests/ -v
```

完整架构指南参见 [CLAUDE.md](CLAUDE.md)。

### 许可证

待定
