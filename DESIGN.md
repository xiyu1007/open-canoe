# Open-Canoe — Design Document / 设计文档

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>
## English

### 1. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         APP (PC Side)                            │
│                   (Not implemented in this repo)                 │
└──────────────────────────┬───────────────────────────────────────┘
                           │  USART / USB-CDC
                           │  Binary Protocol (see §3)
┌──────────────────────────┴───────────────────────────────────────┐
│                    HARDWARE FIRMWARE                              │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  main.c (Startup & Main Loop)               │ │
│  │  HAL_Init → Clock → Comm Init → Heartbeat → Event Loop     │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────┴──────────────────────────────────┐ │
│  │              protocol_handler.c (Protocol Layer)            │ │
│  │  Frame encode/decode · CRC16 · Command dispatch            │ │
│  │  Pure C — NO HAL or MCU dependencies                       │ │
│  └───────┬──────────────┬──────────────┬──────────────────────┘ │
│          │              │              │                          │
│  ┌───────┴──┐ ┌─────────┴───┐ ┌───────┴──────────┐              │
│  │ can_api  │ │  adc_api    │ │  comm_api        │              │
│  │ (inc/)   │ │  (inc/)     │ │  (inc/)          │              │
│  └───────┬──┘ └─────────┬───┘ └───────┬──────────┘              │
│          │              │              │                          │
│  ┌───────┴──────────────┴──────────────┴──────────────────┐     │
│  │                  HAL Drivers (src/)                     │     │
│  │  can_driver.c  ·  adc_driver.c  ·  comm_driver.c       │     │
│  │  device_manager.c                                       │     │
│  │  Use macros from device/ config headers                 │     │
│  └──────────────────────────┬──────────────────────────────┘     │
│                              │                                    │
│  ┌──────────────────────────┴──────────────────────────────┐     │
│  │              device/ (MCU Configuration)                 │     │
│  │  stm32f103_config.h  ·  stm32f407_config.h              │     │
│  │  stm32f1xx_hal_conf.h · stm32f4xx_hal_conf.h            │     │
│  │  Pin maps · Clocks · Feature flags · Buffer sizes       │     │
│  └──────────────────────────┬──────────────────────────────┘     │
│                              │                                    │
│  ┌──────────────────────────┴──────────────────────────────┐     │
│  │              STM32 HAL + CMSIS (Drivers/)               │     │
│  │  HAL peripheral drivers · CMSIS Core · Startup · LD     │     │
│  └─────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

### 2. Module Layering

**Layer 0: Hardware (STM32 HAL + CMSIS)**
Third-party STM32 HAL library plus ARM CMSIS. Provides register-level peripheral access. Located in `Drivers/`.

**Layer 1: Device Configuration (`device/`)**
Per-MCU header files defining pin mappings, peripheral base addresses, clock frequencies, feature flags (`HAS_ADC`, `HAS_USB_CDC`, `CAN_INSTANCE_COUNT`), and buffer sizes. **This is the only layer that changes when adding a new MCU.**

**Layer 2: Abstract API (`inc/`)**
Pure header files declaring hardware-independent interfaces:
- `can_api.h` — CAN frame send/receive, mode control, filter, error status
- `adc_api.h` — ADC init, start/stop sampling, read data, capability query
- `comm_api.h` — USART/USB send/receive, interface switching, heartbeat
- `device_api.h` — MCU model, firmware version, capabilities, uptime, serial
- `protocol.h` — Wire protocol frame format, command codes, payload structs

No MCU-specific types (registers, CMSIS) appear in these headers.

**Layer 3: Driver Implementation (`src/`)**
Implementations of the Layer 2 APIs using Layer 1 configuration macros. These files include STM32 HAL headers conditionally based on the target MCU define.

**Layer 4: Protocol Handler (`src/protocol_handler.c`)**
Encodes/decodes the binary protocol, dispatches commands to driver APIs. Pure C with no HAL includes — can be shared with the App side.

**Layer 5: Application (`src/main.c`)**
Startup sequence and main event loop. Initializes hardware in the correct order, sends heartbeat, then loops processing incoming protocol frames.

### 3. Communication Protocol

#### 3.1 Frame Format

```
┌────────┬──────────┬───────┬──────────┬──────────────┬────────┬──────────┐
│ Magic  │ Length   │ Cmd   │ Seq      │ Data         │ CRC16  │ EndMagic │
│ 1 byte │ 2 bytes  │ 1 byte│ 2 bytes  │ 0–256 bytes  │ 2 bytes│ 1 byte   │
│ 0xA5   │ LE u16   │       │ LE u16   │              │ LE u16 │ 0x5A     │
└────────┴──────────┴───────┴──────────┴──────────────┴────────┴──────────┘
├─────────────── HEADER (6 bytes) ──────────────┤├─ DATA ─┤├─ FOOTER (3) ─┤
```

- **Magic**: Fixed `0xA5`, marks frame start.
- **Length**: Total frame length including header, data, footer (LE uint16). Min = 9 (no data), Max = 265.
- **Cmd**: Command or response code (see §3.2).
- **Seq**: Sequence number (LE uint16), incremented per frame. Used for matching requests to responses.
- **Data**: Variable-length payload, command-specific (see §3.3).
- **CRC16**: CRC-CCITT (polynomial `0x1021`, initial value `0xFFFF`) computed over header + data.
- **EndMagic**: Fixed `0x5A`, marks frame end.

#### 3.2 Command Codes

| Code | Name | Direction | Description |
|------|------|-----------|-------------|
| `0x01` | `CMD_GET_INFO` | App→HW | Query firmware version & MCU model |
| `0x02` | `CMD_GET_CAPABILITIES` | App→HW | Query capability bitmap |
| `0x03` | `CMD_GET_STATUS` | App→HW | Query current running status |
| `0x04` | `CMD_GET_ADC_STATUS` | App→HW | Query ADC state |
| `0x10` | `CMD_CAN_SET_BAUDRATE` | App→HW | Configure CAN baudrate |
| `0x11` | `CMD_CAN_SET_MODE` | App→HW | Set CAN mode (normal/listen/loopback) |
| `0x12` | `CMD_CAN_SET_FILTER` | App→HW | Configure CAN acceptance filter |
| `0x20` | `CMD_ADC_SET_SAMPLING` | App→HW | Configure ADC sampling parameters |
| `0x28` | `CMD_COMM_SET_INTERFACE` | App→HW | Switch USART ↔ USB-CDC |
| `0x30` | `CMD_CAN_START_LISTEN` | App→HW | Start CAN message reception |
| `0x31` | `CMD_CAN_STOP_LISTEN` | App→HW | Stop CAN message reception |
| `0x32` | `CMD_ADC_START_SAMPLE` | App→HW | Start ADC waveform sampling |
| `0x33` | `CMD_ADC_STOP_SAMPLE` | App→HW | Stop ADC waveform sampling |
| `0x34` | `CMD_CAN_SEND_FRAME` | App→HW | Transmit a CAN frame |
| `0x3F` | `CMD_SYSTEM_RESET` | App→HW | Soft reset the MCU |
| `0x81` | `MSG_INFO_RESPONSE` | HW→App | Firmware info response |
| `0x82` | `MSG_CAPABILITIES_RESP` | HW→App | Capabilities response |
| `0x83` | `MSG_STATUS_RESPONSE` | HW→App | Status response |
| `0x84` | `MSG_ADC_STATUS_RESP` | HW→App | ADC status response |
| `0x90` | `MSG_CAN_FRAME_UP` | HW→App | Received CAN frame upload |
| `0x91` | `MSG_ADC_DATA_UP` | HW→App | ADC waveform data upload |
| `0x92` | `MSG_ERROR_NOTIFY` | HW→App | Error notification |
| `0x93` | `MSG_DEVICE_HEARTBEAT` | HW→App | Boot identification frame |
| `0xA0` | `MSG_ACK` | HW→App | Command acknowledged |
| `0xA1` | `MSG_NACK` | HW→App | Command rejected (with error code) |

#### 3.3 Payload Structures

See `hardware/inc/protocol.h` for the complete C struct definitions with `#pragma pack(push, 1)`.

**Example: App requests device info**
```
App sends:   A5 09 00 01 00 00  [CRC16] 5A
             │  │       │  │
             │  │       │  └─ Seq=0
             │  │       └── CMD_GET_INFO
             │  └── Length=9 (no data payload)
             └── Magic

HW responds: A5 3B 00 81 00 00 [44-byte device_info_resp_t] [CRC16] 5A
```

**Example: App sends a CAN frame (ID=0x123, DLC=2, data=0xAA,0xBB)**
```
App sends:   A5 13 00 34 01 00 [can_send_frame_t: 14 bytes] [CRC16] 5A
```

#### 3.4 Capability Bitmap

| Bit | Flag | Meaning |
|-----|------|---------|
| 0 | `CAP_ADC` | Hardware ADC waveform sampling available |
| 1 | `CAP_USB_CDC` | USB CDC virtual COM port available |
| 2 | `CAP_MULTI_CAN` | Multiple CAN channels (≥2) |
| 3 | `CAP_TIMESTAMP_US` | Microsecond-precision timestamps |

### 4. Hardware API Design

#### 4.1 CAN API (`can_api.h`)

| Category | Key Operations | Inputs | Outputs |
|---|---|---|---|
| Init/Deinit | `can_init`, `can_deinit` | channel, baudrate, mode | status code |
| Config | `can_set_baudrate`, `can_set_mode`, `can_set_filter` | channel, parameters | status code |
| Send | `can_send_frame` | channel, id, ide, rtr, dlc, data, timeout | status code |
| Receive | `can_receive_frame` | channel, timeout | frame struct with timestamp |
| Callback | `can_register_rx_callback` | channel, function pointer | status code |
| Control | `can_start_listen`, `can_stop_listen` | channel | status code |
| Status | `can_get_error_status`, `can_get_stats`, `can_clear_errors` | channel | error flags, counters, stats |
| Query | `can_get_channel_count`, `can_is_initialized` | channel | count, bool |

#### 4.2 ADC API (`adc_api.h`)

| Category | Key Operations | Inputs | Outputs |
|---|---|---|---|
| Availability | `adc_is_available` | none | bool |
| Init/Deinit | `adc_init`, `adc_deinit` | sample_rate, resolution, channel | status code |
| Control | `adc_start_sampling`, `adc_stop_sampling` | none | status code |
| Read | `adc_read_samples` | timeout | buffer, count, resolution |
| Callback | `adc_register_data_callback` | function pointer | status code |
| Status | `adc_get_status`, `adc_get_max_sample_rate`, `adc_get_resolution` | none | sampling state, rate, bits |

#### 4.3 Communication API (`comm_api.h`)

| Category | Key Operations | Inputs | Outputs |
|---|---|---|---|
| Init/Switch | `comm_init`, `comm_switch_interface` | interface type, baudrate | status code |
| Send/Recv | `comm_send`, `comm_receive` | data, length, timeout | bytes sent/received |
| Callback | `comm_register_rx_callback` | function pointer | status code |
| Heartbeat | `comm_send_heartbeat` | none | status code |
| Status | `comm_is_ready`, `comm_get_current_interface`, `comm_usb_cdc_available` | none | bool, type |

#### 4.4 Device API (`device_api.h`)

| Function | Inputs | Outputs |
|---|---|---|
| `device_get_mcu_model` | none | string |
| `device_get_fw_version` | none | major, minor, patch |
| `device_get_serial` | none | 32-bit unique ID |
| `device_get_info` | none | full info struct |
| `device_get_capabilities` | none | capabilities struct |
| `device_get_uptime_ms` / `_us` | none | ms / μs |
| `device_soft_reset` | none | resets MCU |

### 5. Extending to a New MCU

To add support for a new MCU (e.g., STM32H750), only the following steps are required:

**Step 1: Create `device/stm32h7xx_config.h`**

Define all macros listed below. Refer to `stm32f407_config.h` as a template.

Required macros:
```c
// Identification
#define MCU_MODEL_STRING        "STM32H750VB"
#define MCU_FAMILY_STRING       "STM32H7xx"
#define MCU_CORE_STRING         "Cortex-M7"

// Feature flags
#define HAS_ADC                 1
#define HAS_USB_CDC             1
#define HAS_CAN_LEGACY          0   // H7 uses FDCAN, not legacy bxCAN

// System clocks
#define SYSTEM_CLOCK_HZ         480000000UL
#define APB1_CLOCK_HZ           120000000UL
#define APB2_CLOCK_HZ           120000000UL
#define TIMESTAMP_TIMER_CLK_HZ  1000000UL

// CAN (FDCAN for H7 — requires driver adaptation if not legacy)
#define CAN_INSTANCE_COUNT      2

// Communication
#define COMM_USART              USART1
#define COMM_USART_BAUDRATE     115200

// ADC
#define ADC_INSTANCE            ADC1
#define ADC_SAMPLING_RATE_MAX_HZ  3600000UL

// Buffer sizes
#define CAN_RX_FIFO_SIZE        128
```

**Step 2: Create `device/stm32h7xx_hal_conf.h`**

Enable the necessary HAL modules (CAN/FDCAN, USART, ADC, DMA, etc.) and set oscillator values.

**Step 3: Add platform files**

- `device/h7/startup_stm32h750xx.s` (from STM32CubeMX or CMSIS pack)
- `device/h7/STM32H750XX_FLASH.ld` (linker script)
- `device/h7/system_stm32h7xx.c` (system init)

**Step 4: Create `Makefile_h7`**

Copy `Makefile_f407`, adjust CPU flags (`-mcpu=cortex-m7`), FPU flags, MCU define (`-DSTM32H750xx`), include paths, and source file list.

**Step 5 (if needed): Adapt driver code**

```c
#if defined(STM32H750xx)
  // FDCAN implementation
#else
  // Legacy bxCAN implementation
#endif
```

The key guarantee: **no changes to `inc/` headers or `protocol_handler.c`**.

### 6. Error Handling Strategy

- All API functions return a status code (`xxx_status_t` enum).
- The protocol layer sends `MSG_NACK` with error codes for invalid commands/parameters.
- CAN errors (bus-off, error-passive, CRC, stuff, form, ACK) are reported via `MSG_ERROR_NOTIFY`.
- Hardware faults trigger the `Error_Handler()` trap with LED blink pattern.
- Communication errors result in dropped frames with no retry — the protocol is stateless per-frame.

---

<a name="中文"></a>
## 中文

### 1. 系统架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         APP（PC 端）                              │
│                   （本仓库不实现）                                │
└──────────────────────────┬───────────────────────────────────────┘
                           │  USART / USB-CDC
                           │  二进制协议（见 §3）
┌──────────────────────────┴───────────────────────────────────────┐
│                    硬件固件                                       │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  main.c（启动与主循环）                      │ │
│  │  HAL_Init → 时钟 → 通信初始化 → 心跳 → 事件循环            │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────┴──────────────────────────────────┐ │
│  │              protocol_handler.c（协议层）                   │ │
│  │  帧编解码 · CRC16 · 命令分发                               │ │
│  │  纯 C — 无 HAL 或 MCU 依赖                                 │ │
│  └───────┬──────────────┬──────────────┬──────────────────────┘ │
│          │              │              │                          │
│  ┌───────┴──┐ ┌─────────┴───┐ ┌───────┴──────────┐              │
│  │ can_api  │ │  adc_api    │ │  comm_api        │              │
│  │ (inc/)   │ │  (inc/)     │ │  (inc/)          │              │
│  └───────┬──┘ └─────────┬───┘ └───────┬──────────┘              │
│          │              │              │                          │
│  ┌───────┴──────────────┴──────────────┴──────────────────┐     │
│  │                  HAL 驱动 (src/)                        │     │
│  │  can_driver.c  ·  adc_driver.c  ·  comm_driver.c       │     │
│  │  device_manager.c                                       │     │
│  │  使用 device/ 配置宏                                     │     │
│  └──────────────────────────┬──────────────────────────────┘     │
│                              │                                    │
│  ┌──────────────────────────┴──────────────────────────────┐     │
│  │              device/（MCU 配置）                         │     │
│  │  stm32f103_config.h  ·  stm32f407_config.h              │     │
│  │  stm32f1xx_hal_conf.h · stm32f4xx_hal_conf.h            │     │
│  │  引脚映射 · 时钟 · 功能标志 · 缓冲区大小                │     │
│  └──────────────────────────┬──────────────────────────────┘     │
│                              │                                    │
│  ┌──────────────────────────┴──────────────────────────────┐     │
│  │              STM32 HAL + CMSIS (Drivers/)               │     │
│  │  HAL 外设驱动 · CMSIS Core · 启动 · 链接脚本            │     │
│  └─────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────┘
```

### 2. 模块分层

**第 0 层：硬件（STM32 HAL + CMSIS）**
第三方 STM32 HAL 库加 ARM CMSIS。提供寄存器级外设访问。位于 `Drivers/`。

**第 1 层：设备配置（`device/`）**
每个 MCU 的头文件，定义引脚映射、外设基地址、时钟频率、功能标志（`HAS_ADC`、`HAS_USB_CDC`、`CAN_INSTANCE_COUNT`）和缓冲区大小。**这是添加新 MCU 时唯一需要修改的层。**

**第 2 层：抽象 API（`inc/`）**
纯头文件，声明硬件无关接口：
- `can_api.h` — CAN 帧收发、模式控制、滤波器、错误状态
- `adc_api.h` — ADC 初始化、启停采样、读取数据、能力查询
- `comm_api.h` — USART/USB 收发、接口切换、心跳
- `device_api.h` — MCU 型号、固件版本、能力、运行时间、序列号
- `protocol.h` — 通信协议帧格式、命令码、载荷结构体

这些头文件中不出现任何 MCU 特有类型（寄存器、CMSIS）。

**第 3 层：驱动实现（`src/`）**
使用第 1 层配置宏实现第 2 层 API。这些文件根据目标 MCU 宏有条件地包含 STM32 HAL 头文件。

**第 4 层：协议处理器（`src/protocol_handler.c`）**
编解码二进制协议，将命令分发到驱动 API。纯 C，无 HAL 依赖 —— 可与 App 端共享。

**第 5 层：应用（`src/main.c`）**
启动序列和主事件循环。按正确顺序初始化硬件，发送心跳，然后循环处理传入的协议帧。

### 3. 通信协议

#### 3.1 帧格式

```
┌────────┬──────────┬───────┬──────────┬──────────────┬────────┬──────────┐
│ 魔数   │ 长度     │ 命令  │ 序列号   │ 数据         │ CRC16  │ 尾魔数   │
│ 1 字节 │ 2 字节   │ 1 字节│ 2 字节   │ 0–256 字节   │ 2 字节 │ 1 字节   │
│ 0xA5   │ LE u16   │       │ LE u16   │              │ LE u16 │ 0x5A     │
└────────┴──────────┴───────┴──────────┴──────────────┴────────┴──────────┘
├─────────────── 帧头（6 字节）──────────────┤├─ 数据 ─┤├─ 帧尾（3 字节）─┤
```

- **魔数（Magic）**：固定 `0xA5`，标记帧开始。
- **长度（Length）**：包含帧头、数据、帧尾的总帧长（LE uint16）。最小 = 9（无数据），最大 = 265。
- **命令（Cmd）**：命令或响应码（见 §3.2）。
- **序列号（Seq）**：每帧递增（LE uint16），用于匹配请求与响应。
- **数据（Data）**：变长载荷，具体结构见各命令定义（见 §3.3）。
- **CRC16**：CRC-CCITT（多项式 `0x1021`，初始值 `0xFFFF`），对帧头 + 数据计算。
- **尾魔数（EndMagic）**：固定 `0x5A`，标记帧结束。

#### 3.2 命令码

| 码值 | 名称 | 方向 | 说明 |
|------|------|-----------|-------------|
| `0x01` | `CMD_GET_INFO` | App→HW | 查询固件版本和 MCU 型号 |
| `0x02` | `CMD_GET_CAPABILITIES` | App→HW | 查询能力位图 |
| `0x03` | `CMD_GET_STATUS` | App→HW | 查询当前运行状态 |
| `0x04` | `CMD_GET_ADC_STATUS` | App→HW | 查询 ADC 状态 |
| `0x10` | `CMD_CAN_SET_BAUDRATE` | App→HW | 配置 CAN 波特率 |
| `0x11` | `CMD_CAN_SET_MODE` | App→HW | 设置 CAN 模式（正常/只听/回环） |
| `0x12` | `CMD_CAN_SET_FILTER` | App→HW | 配置 CAN 接收滤波器 |
| `0x20` | `CMD_ADC_SET_SAMPLING` | App→HW | 配置 ADC 采样参数 |
| `0x28` | `CMD_COMM_SET_INTERFACE` | App→HW | 切换 USART ↔ USB-CDC |
| `0x30` | `CMD_CAN_START_LISTEN` | App→HW | 启动 CAN 报文监听 |
| `0x31` | `CMD_CAN_STOP_LISTEN` | App→HW | 停止 CAN 报文监听 |
| `0x32` | `CMD_ADC_START_SAMPLE` | App→HW | 启动 ADC 波形采样 |
| `0x33` | `CMD_ADC_STOP_SAMPLE` | App→HW | 停止 ADC 波形采样 |
| `0x34` | `CMD_CAN_SEND_FRAME` | App→HW | 发送一帧 CAN 报文 |
| `0x3F` | `CMD_SYSTEM_RESET` | App→HW | 软复位 MCU |
| `0x81` | `MSG_INFO_RESPONSE` | HW→App | 固件信息响应 |
| `0x82` | `MSG_CAPABILITIES_RESP` | HW→App | 能力信息响应 |
| `0x83` | `MSG_STATUS_RESPONSE` | HW→App | 状态响应 |
| `0x84` | `MSG_ADC_STATUS_RESP` | HW→App | ADC 状态响应 |
| `0x90` | `MSG_CAN_FRAME_UP` | HW→App | CAN 报文上传 |
| `0x91` | `MSG_ADC_DATA_UP` | HW→App | ADC 波形数据上传 |
| `0x92` | `MSG_ERROR_NOTIFY` | HW→App | 错误通知 |
| `0x93` | `MSG_DEVICE_HEARTBEAT` | HW→App | 设备启动识别帧 |
| `0xA0` | `MSG_ACK` | HW→App | 命令确认 |
| `0xA1` | `MSG_NACK` | HW→App | 命令拒绝（附带错误码） |

#### 3.3 载荷结构体

完整的 C 结构体定义（`#pragma pack(push, 1)`）见 `hardware/inc/protocol.h`。

**示例：App 查询设备信息**
```
App 发送：   A5 09 00 01 00 00  [CRC16] 5A
             │  │       │  │
             │  │       │  └─ Seq=0
             │  │       └── CMD_GET_INFO
             │  └── 长度=9（无数据载荷）
             └── 魔数

HW 响应：   A5 3B 00 81 00 00 [44 字节 device_info_resp_t] [CRC16] 5A
```

**示例：App 发送一帧 CAN 报文（ID=0x123, DLC=2, 数据=0xAA,0xBB）**
```
App 发送：   A5 13 00 34 01 00 [can_send_frame_t: 14 字节] [CRC16] 5A
```

#### 3.4 能力位图

| 位 | 标志 | 含义 |
|-----|------|---------|
| 0 | `CAP_ADC` | 硬件 ADC 波形采样可用 |
| 1 | `CAP_USB_CDC` | USB CDC 虚拟串口可用 |
| 2 | `CAP_MULTI_CAN` | 多 CAN 通道（≥2） |
| 3 | `CAP_TIMESTAMP_US` | 微秒精度时间戳 |

### 4. 硬件 API 设计

#### 4.1 CAN API（`can_api.h`）

| 类别 | 关键操作 | 输入 | 输出 |
|---|---|---|---|
| 初始化/反初始化 | `can_init`, `can_deinit` | 通道、波特率、模式 | 状态码 |
| 配置 | `can_set_baudrate`, `can_set_mode`, `can_set_filter` | 通道、参数 | 状态码 |
| 发送 | `can_send_frame` | 通道、id、ide、rtr、dlc、数据、超时 | 状态码 |
| 接收 | `can_receive_frame` | 通道、超时 | 含时间戳的帧结构体 |
| 回调 | `can_register_rx_callback` | 通道、函数指针 | 状态码 |
| 控制 | `can_start_listen`, `can_stop_listen` | 通道 | 状态码 |
| 状态 | `can_get_error_status`, `can_get_stats`, `can_clear_errors` | 通道 | 错误标志、计数器、统计 |
| 查询 | `can_get_channel_count`, `can_is_initialized` | 通道 | 数量、布尔值 |

#### 4.2 ADC API（`adc_api.h`）

| 类别 | 关键操作 | 输入 | 输出 |
|---|---|---|---|
| 可用性 | `adc_is_available` | 无 | 布尔值 |
| 初始化/反初始化 | `adc_init`, `adc_deinit` | 采样率、分辨率、通道 | 状态码 |
| 控制 | `adc_start_sampling`, `adc_stop_sampling` | 无 | 状态码 |
| 读取 | `adc_read_samples` | 超时 | 缓冲区、数量、分辨率 |
| 回调 | `adc_register_data_callback` | 函数指针 | 状态码 |
| 状态 | `adc_get_status`, `adc_get_max_sample_rate`, `adc_get_resolution` | 无 | 采样状态、采样率、位数 |

#### 4.3 通信 API（`comm_api.h`）

| 类别 | 关键操作 | 输入 | 输出 |
|---|---|---|---|
| 初始化/切换 | `comm_init`, `comm_switch_interface` | 接口类型、波特率 | 状态码 |
| 收发 | `comm_send`, `comm_receive` | 数据、长度、超时 | 收发字节数 |
| 回调 | `comm_register_rx_callback` | 函数指针 | 状态码 |
| 心跳 | `comm_send_heartbeat` | 无 | 状态码 |
| 状态 | `comm_is_ready`, `comm_get_current_interface`, `comm_usb_cdc_available` | 无 | 布尔值、类型 |

#### 4.4 设备 API（`device_api.h`）

| 函数 | 输入 | 输出 |
|---|---|---|
| `device_get_mcu_model` | 无 | 字符串 |
| `device_get_fw_version` | 无 | 主版本、次版本、补丁版本 |
| `device_get_serial` | 无 | 32 位唯一 ID |
| `device_get_info` | 无 | 完整信息结构体 |
| `device_get_capabilities` | 无 | 能力结构体 |
| `device_get_uptime_ms` / `_us` | 无 | 毫秒 / 微秒 |
| `device_soft_reset` | 无 | 复位 MCU |

### 5. 扩展新 MCU

以添加 STM32H750 为例，只需以下步骤：

**步骤 1：创建 `device/stm32h7xx_config.h`**

参考 `stm32f407_config.h` 模板，定义以下所有宏：

```c
// 标识
#define MCU_MODEL_STRING        "STM32H750VB"
#define MCU_FAMILY_STRING       "STM32H7xx"
#define MCU_CORE_STRING         "Cortex-M7"

// 功能标志
#define HAS_ADC                 1
#define HAS_USB_CDC             1
#define HAS_CAN_LEGACY          0   // H7 使用 FDCAN，而非旧式 bxCAN

// 系统时钟
#define SYSTEM_CLOCK_HZ         480000000UL
#define APB1_CLOCK_HZ           120000000UL
#define APB2_CLOCK_HZ           120000000UL
#define TIMESTAMP_TIMER_CLK_HZ  1000000UL

// CAN（H7 用 FDCAN - 需适配驱动）
#define CAN_INSTANCE_COUNT      2

// 通信
#define COMM_USART              USART1
#define COMM_USART_BAUDRATE     115200

// ADC
#define ADC_INSTANCE            ADC1
#define ADC_SAMPLING_RATE_MAX_HZ  3600000UL

// 缓冲区大小
#define CAN_RX_FIFO_SIZE        128
```

**步骤 2：创建 `device/stm32h7xx_hal_conf.h`**

启用必要的 HAL 模块（CAN/FDCAN、USART、ADC、DMA 等）并设置晶振参数。

**步骤 3：添加平台文件**

- `device/h7/startup_stm32h750xx.s`（来自 STM32CubeMX 或 CMSIS 包）
- `device/h7/STM32H750XX_FLASH.ld`（链接脚本）
- `device/h7/system_stm32h7xx.c`（系统初始化）

**步骤 4：创建 `Makefile_h7`**

复制 `Makefile_f407`，调整 CPU 标志（`-mcpu=cortex-m7`）、FPU 标志、MCU 宏（`-DSTM32H750xx`）、include 路径和源文件列表。

**步骤 5（如需要）：适配驱动代码**

```c
#if defined(STM32H750xx)
  // FDCAN 实现
#else
  // 旧式 bxCAN 实现
#endif
```

核心保证：**无需修改 `inc/` 头文件和 `protocol_handler.c`**。

### 6. 错误处理策略

- 所有 API 函数返回状态码（`xxx_status_t` 枚举）。
- 协议层对非法命令/参数发送 `MSG_NACK` 并附带错误码。
- CAN 错误（总线关闭、错误被动、CRC、位填充、格式、应答）通过 `MSG_ERROR_NOTIFY` 上报。
- 硬件故障触发 `Error_Handler()` 陷阱并以 LED 闪烁指示。
- 通信错误导致丢帧，不重试 —— 协议是逐帧无状态的。
