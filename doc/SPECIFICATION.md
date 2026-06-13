# Open-Canoe — Development Specification / 开发规范

**Revision**: 1.0  
**Date**: 2026-06-12  
**Status**: Draft for Implementation  

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>
# English

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Communication Protocol — CANONICAL DEFINITION](#3-communication-protocol)
4. [App–Firmware Interface Contract](#4-appfirmware-interface-contract)
5. [Firmware Architecture](#5-firmware-architecture)
6. [App Architecture](#6-app-architecture)
7. [Integration Implementation Plan](#7-integration-implementation-plan)
8. [Data Flow & State Machines](#8-data-flow--state-machines)
9. [Error Handling Strategy](#9-error-handling-strategy)
10. [Test & Validation Strategy](#10-test--validation-strategy)
11. [Appendix A: Protocol Frame Examples](#appendix-a-protocol-frame-examples)
12. [Appendix B: Migration from Legacy Protocol](#appendix-b-migration-from-legacy-protocol)

---

## 1. Project Overview

Open-Canoe is an open-source CAN bus analyzer consisting of two components:

| Component | Technology | Role |
|-----------|-----------|------|
| **Desktop App** | Python 3.11+ / tkinter | GUI, user interaction, protocol encode/decode |
| **Hardware Probe** | C / STM32 HAL | CAN bus interface, ADC sampling, protocol handling |

The probe communicates with the App via USART or USB-CDC using a custom binary protocol. The architecture enforces strict separation: the protocol layer is shared conceptual design, the App never depends on firmware internals, and new MCU support never requires App changes.

### 1.1 Design Principles

1. **Protocol as contract** — The wire protocol is the sole interface. App and firmware can evolve independently as long as the protocol is honored.
2. **Firmware extensibility** — New MCUs require only a new config directory + Makefile. No changes to `inc/`, `src/`, or App code.
3. **App UI stability** — The existing tkinter GUI layout, widget structure, and interaction patterns are preserved. Only the transport/protocol layer beneath is modified.
4. **Stateless protocol** — Each frame is self-contained. No session state is assumed. ACK/NACK per command.
5. **Graceful degradation** — Features unavailable on hardware (ADC, multi-CAN) are queried at connect time and corresponding UI elements are disabled.

### 1.2 Scope

**Included in this specification:**
- Canonical protocol frame format, command set, and payload structures
- App transport layer refactoring plan
- App→Firmware command flow for every user action
- Firmware→App push data flow (CAN frames, ADC data, errors, heartbeat)
- Error handling contract
- Test strategy

**Out of scope:**
- GUI redesign or new UI features
- New MCU support (architecture preserved for future)
- Firmware driver logic changes (CAN/ADC/COMM drivers are complete)

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DESKTOP APP (Python/tkinter)                   │
│                                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │DeviceBar │  │MsgTable  │  │SendPanel │  │Detail    │             │
│  │(left)    │  │(center)  │  │(right)   │  │(bottom)  │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │             │             │             │                    │
│  ┌────┴─────────────┴─────────────┴─────────────┴────┐               │
│  │                  MainWindow (app.py)               │               │
│  │  - Owns Transport instance                         │               │
│  │  - Polls receive queue at 200ms                    │               │
│  │  - Routes incoming frames → UI updates             │               │
│  │  - Routes UI actions → outgoing commands           │               │
│  └──────────────────────┬─────────────────────────────┘               │
│                         │                                              │
│  ┌──────────────────────┴─────────────────────────────┐               │
│  │              core/protocol.py  (REFACTORED)         │               │
│  │  - Encode: Command + payload → wire bytes           │               │
│  │  - Decode: wire bytes → Frame list                  │               │
│  │  - MUST match firmware/inc/protocol.h               │               │
│  └──────────────────────┬─────────────────────────────┘               │
│                         │                                              │
│  ┌──────────────────────┴─────────────────────────────┐               │
│  │              core/transport.py  (REFACTORED)        │               │
│  │  - SerialTransport: write(bytes), read(bytes)       │               │
│  │  - DeviceDetector: scan ports, heartbeat detection  │               │
│  │  - RecvThread: background read → Queue[Frame]       │               │
│  └──────────────────────┬─────────────────────────────┘               │
│                         │                                              │
└─────────────────────────┼──────────────────────────────────────────────┘
                          │  USART / USB-CDC
                          │  Binary Protocol (see §3)
┌─────────────────────────┴──────────────────────────────────────────────┐
│                       HARDWARE FIRMWARE (C/STM32)                       │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  src/main.c           Startup → Heartbeat → Main Poll Loop        │ │
│  └───────────────────────────────┬───────────────────────────────────┘ │
│                                  │                                      │
│  ┌───────────────────────────────┴───────────────────────────────────┐ │
│  │  src/protocol_handler.c     Encode/Decode · CRC16 · Dispatch     │ │
│  │  (Pure C, no HAL deps — identical logic to App protocol.py)      │ │
│  └───────┬───────────────┬───────────────┬──────────────────────────┘ │
│          │               │               │                             │
│  ┌───────┴──┐ ┌──────────┴──┐ ┌─────────┴──────┐                      │
│  │ can_api  │ │  adc_api    │ │  comm_api      │                      │
│  │ (inc/)   │ │  (inc/)     │ │  (inc/)        │                      │
│  └───────┬──┘ └──────────┬──┘ └─────────┬──────┘                      │
│          │               │              │                              │
│  ┌───────┴───────────────┴──────────────┴─────────────────────────┐   │
│  │  src/can_driver.c · adc_driver.c · comm_driver.c              │   │
│  │  src/device_manager.c                                          │   │
│  │  (Use macros from f103/stm32f103_config.h or f407/...)         │   │
│  └───────────────────────────────┬─────────────────────────────────┘   │
│                                  │                                      │
│  ┌───────────────────────────────┴─────────────────────────────────┐   │
│  │  f103/ · f407/               Per-MCU config + HAL + CMSIS      │   │
│  │  stm32f103_config.h          (ONLY layer changed for new MCU)   │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Layer Ownership

| Layer | Owner | Change Frequency | Constraint |
|-------|-------|------------------|------------|
| Protocol definition | **This spec** | Rare (versioned) | App and firmware must agree |
| App GUI (`gui/`) | App team | Frequent | Never depends on firmware |
| App protocol (`core/protocol.py`) | App team | On protocol version bump | Must match firmware `protocol.h` |
| App transport (`core/transport.py`) | App team | Rare | Implements protocol-aware receive |
| Firmware `inc/protocol.h` | Firmware team | On protocol version bump | Must match App `protocol.py` |
| Firmware `inc/*_api.h` | Firmware team | Rare | Hardware-independent |
| Firmware `src/*_driver.c` | Firmware team | Per-MCU adaptation | Uses config macros only |
| Firmware `f103/`, `f407/` | Firmware team | Per new MCU | CubeMX files NOT modified |

---

## 3. Communication Protocol

**This section is the canonical protocol definition. Both `core/protocol.py` and `firmware/inc/protocol.h` MUST implement exactly this.**

### 3.1 Frame Format

```
Byte Offset:  0      1      2      3      4      5      6..N-4  N-3  N-2  N-1
            ┌──────┬──────┬──────┬──────┬──────┬──────┬───────┬──────┬──────┬──────┐
            │Magic │Length│Length│ Cmd  │ Seq  │ Seq  │ Data  │ CRC16│ CRC16│EndMgc│
            │0xA5  │(lo)  │(hi)  │      │ (lo) │ (hi) │0..255 │ (lo) │ (hi) │0x5A  │
            └──────┴──────┴──────┴──────┴──────┴──────┴───────┴──────┴──────┴──────┘
            ├────────── HEADER (6 bytes) ──────────┤├─ DATA ─┤├─ FOOTER (3) ─────┤
```

| Field | Offset | Size | Type | Description |
|-------|--------|------|------|-------------|
| Magic | 0 | 1 | u8 | Frame start marker, fixed `0xA5` |
| Length | 1 | 2 | u16 LE | **Total** frame length (header + data + footer). Min = 9 (no data), Max = 265 |
| Cmd | 3 | 1 | u8 | Command or response code (§3.2) |
| Seq | 4 | 2 | u16 LE | Monotonic sequence number, wraps at 65535. Responses echo the request seq. Push messages use their own incrementing seq |
| Data | 6 | 0–256 | u8[] | Variable-length payload, structured per command (§3.3) |
| CRC16 | N-3 | 2 | u16 LE | CRC-CCITT (polynomial `0x1021`, init `0xFFFF`) over bytes 0 through N-4 (header + data) |
| EndMagic | N-1 | 1 | u8 | Frame end marker, fixed `0x5A` |

**Constraints:**
- Minimum frame: 9 bytes (header 6 + footer 3, 0 data bytes)
- Maximum frame: 265 bytes (9 + 256 data bytes)
- Length field ALWAYS equals total frame bytes (including itself)
- CRC covers bytes [0, N-4), i.e., header + data, NOT the CRC field itself or EndMagic
- Sequence numbers: App-originated commands use App's counter; firmware push messages (0x90–0x93) use firmware's counter; responses (0x81–0x84, 0xA0–0xA1) echo the request's seq

### 3.2 Command Codes

#### 3.2.1 App → Firmware Commands (0x01–0x3F)

| Code | Name | Payload Struct | Description |
|------|------|---------------|-------------|
| `0x01` | `CMD_GET_INFO` | (none) | Query firmware version, MCU model, serial |
| `0x02` | `CMD_GET_CAPABILITIES` | (none) | Query capability bitmap |
| `0x03` | `CMD_GET_STATUS` | (none) | Query running status (CAN listening, ADC sampling, uptime) |
| `0x04` | `CMD_GET_ADC_STATUS` | (none) | Query ADC state |
| `0x10` | `CMD_CAN_SET_BAUDRATE` | `can_set_baudrate_t` | Configure CAN baudrate (Hz) |
| `0x11` | `CMD_CAN_SET_MODE` | `can_set_mode_t` | Set CAN mode (normal/listen-only/loopback/loopback-silent) |
| `0x12` | `CMD_CAN_SET_FILTER` | `can_set_filter_t` | Configure CAN acceptance filter |
| `0x20` | `CMD_ADC_SET_SAMPLING` | `adc_set_sampling_t` | Configure ADC parameters |
| `0x28` | `CMD_COMM_SET_INTERFACE` | `comm_set_interface_t` | Switch USART ↔ USB-CDC |
| `0x30` | `CMD_CAN_START_LISTEN` | (none) | Start CAN message reception |
| `0x31` | `CMD_CAN_STOP_LISTEN` | (none) | Stop CAN message reception |
| `0x32` | `CMD_ADC_START_SAMPLE` | (none) | Start ADC waveform sampling |
| `0x33` | `CMD_ADC_STOP_SAMPLE` | (none) | Stop ADC waveform sampling |
| `0x34` | `CMD_CAN_SEND_FRAME` | `can_send_frame_t` | Transmit a CAN frame on the bus |
| `0x3F` | `CMD_SYSTEM_RESET` | (none) | Soft reset the MCU |

#### 3.2.2 Firmware → App Responses (0x81–0x84)

| Code | Name | Payload Struct | Description |
|------|------|---------------|-------------|
| `0x81` | `MSG_INFO_RESPONSE` | `device_info_resp_t` | Response to `CMD_GET_INFO` |
| `0x82` | `MSG_CAPABILITIES_RESP` | `capabilities_resp_t` | Response to `CMD_GET_CAPABILITIES` |
| `0x83` | `MSG_STATUS_RESPONSE` | `status_resp_t` | Response to `CMD_GET_STATUS` |
| `0x84` | `MSG_ADC_STATUS_RESP` | (7-byte raw) | Response to `CMD_GET_ADC_STATUS` |

#### 3.2.3 Firmware → App Push Messages (0x90–0x93)

| Code | Name | Payload Struct | Trigger |
|------|------|---------------|---------|
| `0x90` | `MSG_CAN_FRAME_UP` | `can_frame_up_t` | CAN frame received by hardware (RX or loopback TX echo) |
| `0x91` | `MSG_ADC_DATA_UP` | `adc_data_up_t` | ADC sample buffer half/full DMA callback |
| `0x92` | `MSG_ERROR_NOTIFY` | `error_notify_t` | CAN bus error, hardware fault |
| `0x93` | `MSG_DEVICE_HEARTBEAT` | `device_heartbeat_t` | Sent once on boot, after comm init |

#### 3.2.4 Firmware → App Acknowledgments (0xA0–0xA1)

| Code | Name | Payload Struct | Description |
|------|------|---------------|-------------|
| `0xA0` | `MSG_ACK` | `ack_resp_t` | Command succeeded (`error_code == 0`) or failed with error |
| `0xA1` | `MSG_NACK` | (none) | Command rejected (invalid params) — **legacy, prefer MSG_ACK with error_code** |

**Rule**: Firmware SHOULD respond with `MSG_ACK` (with `error_code` field) for all config/control commands. `MSG_NACK` is retained for backward compatibility but new code should use `MSG_ACK`.

### 3.3 Payload Structures

All multi-byte integers are **little-endian**. All structs are **packed** (no alignment padding).

```c
// CAN frame send (App → FW, CMD_CAN_SEND_FRAME)
can_send_frame_t {
    uint32_t can_id;       // CAN ID (11-bit or 29-bit)
    uint8_t  dlc;          // Data length 0–8
    uint8_t  flags;        // bit0: IDE (1=extended), bit1: RTR (1=remote)
    uint8_t  channel;      // CAN channel index (0-based)
    uint8_t  data[8];      // CAN data bytes (only first dlc bytes valid)
}
// Total: 15 bytes

// CAN frame upload (FW → App, MSG_CAN_FRAME_UP)
can_frame_up_t {
    uint32_t timestamp;    // Hardware timestamp in μs
    uint32_t can_id;       // CAN ID
    uint8_t  dlc;          // Data length 0–8
    uint8_t  flags;        // bit0: IDE, bit1: RTR, bit2: error_frame
    uint8_t  data[8];      // CAN data bytes
    uint8_t  channel;      // CAN channel index
}
// Total: 20 bytes

// Device info response (FW → App, MSG_INFO_RESPONSE)
device_info_resp_t {
    uint8_t  fw_major;
    uint8_t  fw_minor;
    uint8_t  fw_patch;
    uint8_t  reserved;
    uint16_t protocol_version;  // (major << 8) | minor
    char     mcu_model[32];
    char     fw_description[32];
    uint32_t device_serial;
}
// Total: 76 bytes

// Capabilities response (FW → App, MSG_CAPABILITIES_RESP)
capabilities_resp_t {
    uint32_t capability_bits;    // CAP_ADC | CAP_USB_CDC | CAP_MULTI_CAN | CAP_TIMESTAMP_US
    uint8_t  can_channel_count;
    uint32_t max_adc_sample_rate;
    uint8_t  adc_resolution;
    uint16_t max_can_baudrate;   // kbps
}
// Total: 12 bytes

// CAN baudrate config (App → FW, CMD_CAN_SET_BAUDRATE)
can_set_baudrate_t {
    uint32_t baudrate;           // Hz (e.g., 500000)
    uint8_t  channel;
}
// Total: 5 bytes

// CAN mode config (App → FW, CMD_CAN_SET_MODE)
can_set_mode_t {
    uint8_t channel;
    uint8_t mode;                // 0=normal, 1=listen-only, 2=loopback, 3=loopback+silent
}
// Total: 2 bytes

// CAN filter config (App → FW, CMD_CAN_SET_FILTER)
can_set_filter_t {
    uint8_t  channel;
    uint8_t  filter_index;
    uint8_t  filter_mode;        // 0=id_mask, 1=id_list
    uint8_t  filter_scale;       // 0=16bit, 1=32bit
    uint32_t id_high;
    uint32_t id_low;
    uint32_t mask_high;
    uint32_t mask_low;
}
// Total: 20 bytes

// ADC sampling config (App → FW, CMD_ADC_SET_SAMPLING)
adc_set_sampling_t {
    uint32_t sample_rate;        // Hz
    uint8_t  resolution;         // bits (12)
    uint8_t  channel;
}
// Total: 6 bytes

// Comm interface switch (App → FW, CMD_COMM_SET_INTERFACE)
comm_set_interface_t {
    uint8_t interface;           // 0=USART, 1=USB_CDC
}
// Total: 1 byte

// Error notification (FW → App, MSG_ERROR_NOTIFY)
error_notify_t {
    uint8_t  error_code;
    uint8_t  source_module;      // 0=CAN, 1=ADC, 2=COMM, 3=SYSTEM
    uint16_t error_flags;
    uint32_t timestamp;
}
// Total: 8 bytes

// Status response (FW → App, MSG_STATUS_RESPONSE)
status_resp_t {
    uint8_t  can_listening;
    uint8_t  adc_sampling;
    uint8_t  comm_interface;
    uint8_t  can_channels_active; // Bitmap
    uint32_t uptime_ms;
}
// Total: 8 bytes

// ACK/NACK (FW → App, MSG_ACK)
ack_resp_t {
    uint8_t  ack_cmd;            // Original command code being acked
    uint8_t  error_code;         // 0=success, see error codes
}
// Total: 2 bytes

// Heartbeat (FW → App, MSG_DEVICE_HEARTBEAT)
device_heartbeat_t {
    char     mcu_model[32];
    uint8_t  fw_major;
    uint8_t  fw_minor;
    uint8_t  fw_patch;
    uint8_t  comm_interface;
}
// Total: 36 bytes

// ADC data upload (FW → App, MSG_ADC_DATA_UP)
adc_data_up_t {
    uint32_t timestamp;
    uint32_t sample_rate;
    uint16_t sample_count;
    uint16_t resolution;
    uint8_t  channel;
    uint8_t  mode;               // 0=ADC hardware, 1=logic-level
    uint16_t samples[];          // Variable-length array
}
// Header: 14 bytes + 2*sample_count
```

### 3.4 Capability Bitmap

| Bit | Constant | Meaning | App UI Effect |
|-----|----------|---------|---------------|
| 0 | `CAP_ADC` (1<<0) | Hardware ADC available | Enable waveform ADC mode |
| 1 | `CAP_USB_CDC` (1<<1) | USB CDC available | Show USB CDC option in port dropdown |
| 2 | `CAP_MULTI_CAN` (1<<2) | Multiple CAN channels | Enable channel selector (future) |
| 3 | `CAP_TIMESTAMP_US` (1<<3) | μs-precision timestamps | Display μs in message table |

### 3.5 Error Codes

| Code | Name | Meaning |
|------|------|---------|
| `0x00` | `ERR_NONE` | Success |
| `0x01` | `ERR_INVALID_CMD` | Unknown command code |
| `0x02` | `ERR_INVALID_PARAM` | Parameter out of range |
| `0x03` | `ERR_CRC_MISMATCH` | Frame CRC check failed |
| `0x04` | `ERR_BUFFER_OVERFLOW` | RX buffer overflow |
| `0x05` | `ERR_TIMEOUT` | Operation timed out |
| `0x10` | `ERR_CAN_BUS_OFF` | CAN bus-off state |
| `0x11` | `ERR_CAN_ERROR_PASSIVE` | CAN error-passive state |
| `0x12` | `ERR_CAN_TX_FAILED` | CAN transmission failed |
| `0x13` | `ERR_CAN_RX_OVERRUN` | CAN receive overrun |
| `0x20` | `ERR_ADC_NOT_AVAILABLE` | ADC not present on this MCU |
| `0x21` | `ERR_ADC_OVERRUN` | ADC sample overrun |
| `0x30` | `ERR_COMM_TX_FAILED` | Communication TX failed |
| `0x31` | `ERR_COMM_RX_OVERRUN` | Communication RX overrun |
| `0x40` | `ERR_NOT_INITIALIZED` | Peripheral not initialized |
| `0x41` | `ERR_ALREADY_RUNNING` | Operation already in progress |
| `0xFF` | `ERR_HARDWARE_FAULT` | Unrecoverable hardware error |

---

## 4. App–Firmware Interface Contract

This section defines the exact sequence of protocol interactions for every user-visible operation. The App implementation MUST follow these sequences.

### 4.1 Connection & Discovery

```
User clicks "Connect"
  │
  ▼
App: Open serial port (selected or auto-detected)
  │
  ▼
App: Wait for MSG_DEVICE_HEARTBEAT (timeout: 2000ms)
  │  ◄── FW sends heartbeat automatically on boot
  │
  ├─ Heartbeat received ──► App updates UI: MCU model, FW version
  │                          App shows "● Connected — COMx"
  │
  └─ Timeout ──► App retries with different baudrate (115200 → 921600)
                  If all fail: show "No CAN probe detected"
```

### 4.2 Capability Query (immediately after heartbeat)

```
App: CMD_GET_CAPABILITIES → FW
  │
  ▼
FW: MSG_CAPABILITIES_RESP ← {
      capability_bits: CAP_ADC | CAP_TIMESTAMP_US,
      can_channel_count: 1,
      max_adc_sample_rate: 2400000,
      adc_resolution: 12,
      max_can_baudrate: 1000,
    }
  │
  ▼
App: Update UI based on capabilities:
  - !CAP_ADC  → disable waveform "Capture" button, show "ADC not available"
  - CAP_MULTI_CAN → show channel selector
  - max_can_baudrate → limit baudrate dropdown
```

### 4.3 CAN Configuration & Start

```
User selects baudrate 500k, clicks "Connect" (or changes baudrate while connected)
  │
  ▼
App: CMD_CAN_SET_BAUDRATE { baudrate: 500000, channel: 0 } → FW
  │
  ▼
FW: MSG_ACK { ack_cmd: 0x10, error_code: 0x00 } ←
  │
  ▼
App: CMD_CAN_SET_MODE { channel: 0, mode: 0 (normal) or 1 (listen-only) } → FW
  │
  ▼
FW: MSG_ACK { ack_cmd: 0x11, error_code: 0x00 } ←
  │
  ▼
App: CMD_CAN_START_LISTEN → FW
  │
  ▼
FW: MSG_ACK { ack_cmd: 0x30, error_code: 0x00 } ←
  │  FW also activates CAN RX interrupts
  │
  ▼
FW: MSG_CAN_FRAME_UP { ... } ← begins streaming received CAN frames
  │
  ▼
App: MessageTable.add() for each received frame
     Stats updated in status bar
```

### 4.4 Send CAN Frame

```
User fills composer, clicks "Send Once"
  │
  ▼
App: (GUI-only) MessageTable.add(msg, is_tx=True)  ← immediate local display
  │
  ▼
App: CMD_CAN_SEND_FRAME { can_id, dlc, flags, channel, data } → FW
  │
  ▼
FW: Attempts CAN TX
  │
  ├─ Success → FW: MSG_ACK { ack_cmd: 0x34, error_code: 0x00 } ←
  │              FW also echoes: MSG_CAN_FRAME_UP { ... flags with TX indication }
  │              (If not in loopback mode, TX doesn't trigger RX)
  │
  └─ Failure → FW: MSG_ACK { ack_cmd: 0x34, error_code: ERR_CAN_TX_FAILED } ←
                 App shows error in log panel
```

### 4.5 Cycle Send

```
User clicks "Start Cycle" with interval=100ms
  │
  ▼
App: every 100ms:
       MessageTable.add(msg, is_tx=True)
       CMD_CAN_SEND_FRAME → FW
  │
  ▼
User clicks "Stop Cycle"
  │
  ▼
App: cancels after() scheduled send
```

**Note**: Cycle timing is App-side only. Firmware has no cycle concept — it just executes individual `CMD_CAN_SEND_FRAME` commands.

### 4.6 Disconnect

```
User clicks "Disconnect"
  │
  ▼
App: CMD_CAN_STOP_LISTEN → FW
  │  (best-effort, may fail if already disconnected)
  │
  ▼
App: Transport.disconnect() — close serial port
  │
  ▼
App: UI → disconnected state, clear stats
```

### 4.7 Silent Mode Toggle

```
User checks "Silent mode"
  │
  ▼
App: CMD_CAN_SET_MODE { channel: 0, mode: 1 (listen-only) } → FW
  │  App: SendPanel.set_enabled(False) — disable send buttons
  │
  ▼
User unchecks "Silent mode"
  │
  ▼
App: CMD_CAN_SET_MODE { channel: 0, mode: 0 (normal) } → FW
  │  App: SendPanel.set_enabled(True)
```

### 4.8 Waveform Probe

```
User opens Waveform window, clicks "Capture"
  │
  ▼
App: CMD_GET_ADC_STATUS → FW  (check availability)
  │
  ▼
FW: MSG_ADC_STATUS_RESP ←
  │
  ├─ ADC available → App: CMD_ADC_SET_SAMPLING { rate, resolution, channel } → FW
  │                   App: CMD_ADC_START_SAMPLE → FW
  │                   FW: MSG_ADC_DATA_UP { ... } ← begins streaming
  │                   App: waveform_window.update(data)
  │
  └─ ADC unavailable → App: show "ADC not available on this device"
                         waveform canvas shows placeholder
```

### 4.9 Firmware Flash

```
User clicks "Flash Firmware..."
  │
  ▼
App: Shows dialog with MCU selection (F103/F407)
  │
  ▼
User selects MCU, clicks OK
  │
  ▼
App: Disconnects from device
  │  Runs: uv run python tools/deploy.py
  │  Captures JSON output, displays progress
  │
  ▼
App: Reconnects, receives new heartbeat
  │  Updates UI with new FW version
```

### 4.10 Message Filtering

**All filtering is App-side.** The firmware does NOT do software filtering beyond hardware CAN filter banks.

```
App receives MSG_CAN_FRAME_UP
  │
  ▼
App: Creates CANMessage from can_frame_up_t
  │
  ▼
App: Checks display_filter (show/hide/off)
  │  If filtered OUT → skip display, still count in stats
  │
  ▼
App: Checks msg_filter (show/hide/off)
  │  If filtered OUT → skip entirely (not displayed, not counted)
  │
  ▼
App: Checks TX/RX toggle state
  │  If TX-only and frame is RX → skip display
  │  If RX-only and frame is TX → skip display
  │
  ▼
App: MessageTable.add(msg) — insert into Treeview
```

---

## 5. Firmware Architecture

### 5.1 Directory Structure (PRESERVED)

```
firmware/
├── inc/                          # Hardware-independent headers
│   ├── protocol.h                # Wire format, command codes, payload structs
│   ├── can_api.h                 # CAN driver abstract interface
│   ├── adc_api.h                 # ADC driver abstract interface
│   ├── comm_api.h                # Communication driver abstract interface
│   ├── device_api.h              # Device info & capability query
│   └── device_config.h           # Auto-includes MCU config based on -D flag
├── src/                          # Shared firmware source
│   ├── main.c                    # Entry point, startup sequence, main loop
│   ├── protocol_handler.c        # Frame encode/decode, CRC16, command dispatch
│   ├── can_driver.c              # bxCAN driver (F103 + F407)
│   ├── adc_driver.c              # ADC driver with DMA (optional, HAS_ADC)
│   ├── comm_driver.c             # USART + USB CDC driver
│   ├── device_manager.c          # Device identity, capabilities, uptime
│   ├── sysmem.c                  # Memory stubs (from CubeMX, DO NOT MODIFY)
│   └── syscalls.c                # System call stubs (from CubeMX, DO NOT MODIFY)
├── f103/                         # STM32F103C8T6 — ALL MCU-specific files
│   ├── stm32f103_config.h        # Pin map, clocks, features, buffer sizes
│   ├── stm32f1xx_hal_conf.h      # HAL module selection
│   ├── startup_stm32f103xb.s     # From CubeMX, DO NOT MODIFY
│   ├── STM32F103XX_FLASH.ld      # From CubeMX, DO NOT MODIFY
│   ├── system_stm32f1xx.c        # From CubeMX, DO NOT MODIFY
│   ├── CMSIS/                    # From CubeMX, DO NOT MODIFY
│   └── HAL/                      # From CubeMX, DO NOT MODIFY
│       ├── Inc/ (all files)
│       └── Src/ (used modules only: hal, can, adc, uart, usart, dma, gpio, gpio_ex,
│                  rcc, rcc_ex, cortex, flash, flash_ex, pwr, exti, tim)
├── f407/                         # STM32F407VET6 — same structure as f103/
├── Makefile_f103
└── Makefile_f407
```

### 5.2 Startup Sequence

```
Power-on / Reset
  │
  ▼
1. HAL_Init()
  │
  ▼
2. SystemClock_Config()
   - F103: HSI → PLL → 72 MHz
   - F407: HSE (24 MHz) → PLL → 168 MHz
  │
  ▼
3. HAL_SYSTICK_Config()  — re-init for 1ms tick
  │
  ▼
4. GPIO_Init()  — debug LED
  │
  ▼
5. TimestampTimer_Init()  — TIM2, free-running 1 MHz counter
  │
  ▼
6. comm_init(COMM_IF_USART, 115200)
   - USART GPIO, NVIC, HAL_UART_Receive_IT for 1-byte RX
   - USB CDC (F407 only) if available
  │
  ▼
7. protocol_send_heartbeat()  — MSG_DEVICE_HEARTBEAT frame
  │
  ▼
8. can_register_rx_callback() for all channels
   adc_register_data_callback()
  │
  ▼
9. Main Loop (infinite):
     comm_receive() → protocol_process_buffer()
     Protocol handler dispatches commands via dispatch table
     CAN frames arrive via ISR → callback → protocol_send_can_frame()
```

### 5.3 Adding a New MCU (Extensibility PRESERVED)

To add e.g., STM32H750VB:

1. **Create `firmware/h7/`** with CubeMX files (startup, linker, system, CMSIS, HAL)
2. **Create `stm32h7xx_config.h`** — define all macros listed in existing config headers
3. **Create `stm32h7xx_hal_conf.h`** — enable required HAL modules
4. **Create `Makefile_h7`** — copy existing, adjust `MCU_DIR`, CPU/FPU flags, `-D` define
5. **Register in `tools/deploy.py`** TARGETS dict
6. **If FDCAN (non-legacy)**: add `#if defined(STM32H750xx)` sections in `can_driver.c`
7. **No changes to `inc/`, other `src/` files, or App code**

### 5.4 Key Constraints

- `inc/` headers contain NO MCU-specific types, registers, or CMSIS includes
- `protocol_handler.c` is pure C — no HAL includes
- CubeMX-origin files (`startup_*.s`, `*_FLASH.ld`, `system_*.c`, `CMSIS/`, `HAL/`, `sysmem.c`, `syscalls.c`) are NEVER modified
- MCU differences handled through `device_config.h` → per-MCU `*_config.h` macros
- All driver API functions return a status code enum

---

## 6. App Architecture

### 6.1 Directory Structure (PRESERVED)

```
open-canoe/
├── main.py                       # Entry: uv run python main.py
├── pyproject.toml                # Dependencies: pyserial, pyyaml
├── config/
│   └── defaults.yaml             # Single configuration file
├── core/
│   ├── models.py                 # CANMessage, BusStatistics (dataclasses)
│   ├── protocol.py               # Protocol encode/decode
│   └── transport.py              # Serial transport + device detection
└── gui/
    ├── app.py                    # MainWindow orchestrator
    ├── config.py                 # Colors, fonts, bitrates, load_config()
    ├── lang.py                   # ZH/EN string tables
    ├── device_bar.py             # Left sidebar
    ├── message_table.py          # Center: ttk.Treeview, collapse, offload
    ├── send_panel.py             # Right: composer, cycle, filter
    ├── detail_panel.py           # Bottom: raw/decoded view
    ├── log_panel.py              # Bottom: colored log
    ├── history_window.py         # Popup: regex search, export
    └── waveform_window.py        # Popup: oscilloscope
```

### 6.2 GUI Component Rules

1. **All user-facing strings** → `gui/lang.py` `L()` dict. Add new keys to both ZH and EN tables.
2. **All colors/fonts** → `gui/config.py`. Never hardcode in widgets.
3. **GUI components never import firmware headers.** All communication via `core/protocol.py` and `core/transport.py`.
4. **GUI never blocks.** Serial I/O in background thread; results via `queue.Queue` polled by `app.py._poll()` at 200ms.
5. **Layout is defined in `app.py._relayout()` only.** Panels added/removed from PanedWindow panes.

### 6.3 App-Side Protocol Layer (Refactoring Target)

The current `core/protocol.py` implements a DIFFERENT wire format from firmware. This is the primary integration task.

**Current (BROKEN — does not match firmware):**
```python
# Wire format: 0xAA | CMD(1B) | LEN(2B LE) | PAYLOAD | CRC16(2B LE) | 0x55
# Different magic bytes, different field order, different command codes
```

**Target (MUST match firmware `protocol.h`):**
```python
# Wire format: 0xA5 | LEN(2B LE) | CMD(1B) | SEQ(2B LE) | PAYLOAD | CRC16(2B LE) | 0x5A
# Same magic, same field order, same command codes as firmware
```

### 6.4 App-Side Transport Layer (Refactoring Target)

The current transport layer does raw serial read/write with no protocol framing. It needs:

1. **Background read thread** — continuously reads from serial, feeds bytes to protocol decoder
2. **Frame dispatch** — routes decoded frames to appropriate handlers based on command code
3. **Sequence number tracking** — increments seq per outgoing command
4. **ACK/response matching** — for commands expecting ACK, track pending seq numbers
5. **Heartbeat detection** — on connect, wait for `MSG_DEVICE_HEARTBEAT` to confirm device type
6. **Capability cache** — after `CMD_GET_CAPABILITIES`, cache result for UI decisions

### 6.5 Required App Changes Summary

| File | Change | Reason |
|------|--------|--------|
| `core/protocol.py` | **REWRITE** | Match firmware wire format (§3) |
| `core/transport.py` | **REFACTOR** | Add background read thread, frame buffering, heartbeat detection |
| `gui/app.py` | **MINOR** | Wire up connect→heartbeat→capabilities flow; handle incoming CAN frames |
| `gui/device_bar.py` | **MINOR** | Populate port dropdown from transport; display MCU info after connect |
| `gui/waveform_window.py` | **MINOR** | Feed ADC data from transport to Canvas renderer |
| All other `gui/*.py` | **NONE** | UI widgets unchanged |

---

## 7. Integration Implementation Plan

### Phase 1: Protocol Alignment (CRITICAL PATH)

**Task 1.1**: Rewrite `core/protocol.py` to match firmware `protocol.h`

- Replace `_STX=0xAA/_ETX=0x55` with `0xA5/0x5A`
- Fix field order: Magic → Length(LE16) → Cmd(1B) → Seq(LE16) → Data → CRC16(LE16) → EndMagic
- Replace `Command` IntEnum with firmware's `protocol_cmd_t` values
- Add all payload struct encode/decode functions as Python `struct` format strings
- Add CRC16-CCITT with correct polynomial `0x1021`, initial `0xFFFF`
- Add sequence number state management
- Output: `protocol.py` that can encode/decode every frame type in §3

**Task 1.2**: Verify protocol round-trip

- Write unit test: encode CAN_SEND_FRAME in Python → decode with C logic → assert match
- Write unit test: encode MSG_INFO_RESPONSE in C → decode in Python → assert match
- Test CRC edge cases (empty payload, max-length payload)

### Phase 2: Transport Refactoring

**Task 2.1**: Add `FrameReceiver` class to `core/transport.py`

```python
class FrameReceiver:
    """Buffers serial bytes, extracts complete protocol frames."""
    def feed(self, data: bytes) -> list[Frame]: ...
    def reset(self) -> None: ...
```

**Task 2.2**: Add background read thread to `SerialTransport`

```python
class SerialTransport(AbstractTransport):
    def connect(self) -> None:
        # Open serial port
        # Start self._rx_thread: while self._running: data = read(); queue.put(frames)
    def incoming(self) -> list[Frame]:
        # Non-blocking: return all queued frames
```

**Task 2.3**: Add device detection to `auto_detect()`

```python
def auto_detect(baudrate: int = 115200) -> AbstractTransport:
    """Try each port, listen for MSG_DEVICE_HEARTBEAT."""
    # For each port:
    #   Open, wait 2000ms for heartbeat frame
    #   If heartbeat received → return transport
    #   Else → close, try next port
```

### Phase 3: App Integration

**Task 3.1**: Refactor `app.py._connect_async()` to use new flow

```python
def _connect_async(self) -> None:
    # 1. Open transport
    # 2. Wait for heartbeat → extract MCU model, FW version
    # 3. Send CMD_GET_CAPABILITIES → cache capabilities
    # 4. Send CMD_GET_INFO → display in UI
    # 5. Configure CAN: baudrate, mode, filter
    # 6. Start CAN listening
    # 7. Begin polling receive queue
```

**Task 3.2**: Add incoming frame handler in `app.py`

```python
def _handle_frame(self, frame: Frame) -> None:
    """Route incoming protocol frames to appropriate handlers."""
    match frame.command:
        case Command.CAN_FRAME_UP:
            msg = self._decode_can_frame(frame.payload)
            self._tbl.add(msg, is_tx=False)
        case Command.ERROR_NOTIFY:
            self._log.log(error_message, "err")
        case Command.ACK:
            self._handle_ack(frame.payload)
        case Command.HEARTBEAT:
            self._handle_heartbeat(frame.payload)
        # etc.
```

**Task 3.3**: Wire device_bar.py to reflect connected device info

- After capabilities query: update MCU label, show CAN channel count
- After info query: show FW version string
- If ADC unavailable: disable waveform button

### Phase 4: Demo Mode Preservation

The app MUST continue to work in demo mode (no hardware connected). The existing demo mode behavior (local message echo, no transport required) is preserved:

```python
# In _on_send:
if self._tr and self._tr.is_connected:
    self._tr.write(encode(CMD_CAN_SEND_FRAME, payload))
else:
    # Demo mode: message only appears locally (already added by caller)
    pass
```

### Phase 5: Testing

See §10 for full test strategy.

---

## 8. Data Flow & State Machines

### 8.1 App Connection State Machine

```
                    ┌──────────┐
                    │DISCONNECT│
                    └────┬─────┘
                         │ User clicks "Connect"
                         ▼
                    ┌──────────┐
                    │SCANNING  │──► Auto-detect loops through COM ports
                    └────┬─────┘
                         │ Port opened
                         ▼
                    ┌──────────┐
                    │WAIT_HB   │──► Wait 2000ms for MSG_DEVICE_HEARTBEAT
                    └────┬─────┘
                         │
              ┌──────────┼──────────┐
              │ HB rcvd  │ Timeout  │
              ▼          ▼          │
         ┌────────┐ ┌─────────┐    │
         │QUERY   │ │RETRY    │────┘ (next port or baudrate)
         │CAPS    │ │NEXT     │
         └───┬────┘ └─────────┘
             │ CMD_GET_CAPABILITIES → FW
             ▼
         ┌────────┐
         │CONFIG  │──► CMD_CAN_SET_BAUDRATE → FW
         │CAN     │──► CMD_CAN_SET_MODE → FW
         └───┬────┘
             │
             ▼
         ┌────────┐
         │CONNECT │──► CMD_CAN_START_LISTEN → FW
         │  ED    │    Begin receiving MSG_CAN_FRAME_UP
         └───┬────┘
             │ User clicks "Disconnect"
             ▼
         ┌────────┐
         │DISCONN │──► CMD_CAN_STOP_LISTEN → FW (best-effort)
         │ ECTING │    Close serial port
         └────┬───┘
              │
              ▼
         (back to DISCONNECTED)
```

### 8.2 CAN Message Receive Flow

```
CAN Bus
  │
  ▼
STM32 CAN Peripheral (bxCAN)
  │ RX interrupt
  ▼
can_driver.c: CAN1_IRQHandler()
  │ HAL_CAN_IRQHandler()
  │ can_process_rx_irq()
  ▼
can_frame_t filled with: id, dlc, ide, rtr, data, timestamp
  │ ctx->rx_callback(&frame)
  ▼
protocol_handler.c: can_rx_callback()
  │ protocol_send_can_frame(frame)
  │ → fills can_frame_up_t
  │ → proto_send_data(MSG_CAN_FRAME_UP, ...)
  ▼
comm_driver.c: comm_send()
  │ HAL_UART_Transmit() or USBD_CDC_TransmitPacket()
  ▼
USART/USB-CDC wire
  │
  ▼
App: transport.py FrameReceiver.feed(data)
  │ protocol.decode() → Frame(command=CAN_FRAME_UP, payload=...)
  ▼
App: app.py._handle_frame()
  │ unpack can_frame_up_t → CANMessage dataclass
  ▼
App: message_table.py.add(msg, is_tx=False)
  │ filter checks, collapse logic
  ▼
App: ttk.Treeview row inserted
     stats updated
```

### 8.3 Command-Response Flow

```
App                                   Firmware
  │                                       │
  │── CMD_CAN_SET_BAUDRATE {500000, 0} ──►│
  │                                       │ protocol_process_buffer()
  │                                       │ proto_validate_frame() → CRC OK
  │                                       │ dispatch → handle_can_set_baudrate()
  │                                       │ can_set_baudrate(0, 500000)
  │                                       │   → compute timing params
  │                                       │   → HAL_CAN_Init()
  │                                       │
  │◄── MSG_ACK {CMD_CAN_SET_BAUDRATE, 0}──│
  │                                       │
  │ (App matches seq, confirms ACK)       │
  │                                       │
```

**Timeout rule**: App waits 500ms for ACK. If no response, logs warning. Does NOT retry automatically (user can retry by re-clicking).

---

## 9. Error Handling Strategy

### 9.1 Firmware Errors

| Condition | Firmware Action | App Reaction |
|-----------|----------------|--------------|
| Invalid command code | `MSG_NACK` | Log warning, ignore |
| Invalid parameter | `MSG_ACK` with `ERR_INVALID_PARAM` | Show error in log panel |
| CRC mismatch on incoming frame | Drop frame, reset parser | N/A (firmware discards) |
| CAN bus-off | `MSG_ERROR_NOTIFY` with `ERR_CAN_BUS_OFF` | Show red alert in log, status bar |
| CAN TX mailbox full | `MSG_ACK` with `ERR_CAN_TX_FAILED` | Log "TX failed", increment error counter |
| ADC not available | `MSG_ACK` with `ERR_ADC_NOT_AVAILABLE` | Disable waveform capture UI |
| USART TX failed | Drop frame (ring buffer full) | N/A (rely on ACK timeout) |
| Hardware fault | `Error_Handler()` trap, LED blink | Detect via connection drop |

### 9.2 App Errors

| Condition | App Action |
|-----------|-----------|
| Serial port open fails | Show messagebox, stay disconnected |
| No heartbeat within 2000ms | Try next baudrate, then next port, then show "No device found" |
| ACK timeout (500ms) | Log warning, do NOT retry automatically |
| CRC mismatch on incoming frame | Drop frame, increment CRC error counter |
| Device disconnects mid-operation | Detect via serial read exception, set disconnected state, show "Device disconnected" in status bar |
| Protocol version mismatch | Log warning, proceed (best-effort compatibility) |

### 9.3 Graceful Degradation

```
Capability Query Result          UI Behavior
─────────────────────────────────────────────────
CAP_ADC not set                  Waveform window: show "ADC not available"
                                 Disable "Capture" button
CAP_USB_CDC not set              Port dropdown: show only USART ports
CAP_MULTI_CAN not set            No channel selector visible (future feature)
CAN channel count = 1            Use channel 0 only
max_can_baudrate < 1M            Limit baudrate dropdown to supported rates
```

---

## 10. Test & Validation Strategy

### 10.1 Unit Tests (App)

| Test | File | What it verifies |
|------|------|-----------------|
| CRC16 computation | `tests/test_protocol.py` | CRC matches known vectors, matches C implementation |
| Frame encode/decode round-trip | `tests/test_protocol.py` | Encode → Decode returns same data for all command types |
| CAN_SEND_FRAME encoding | `tests/test_protocol.py` | Python-encoded frame matches C-expected bytes |
| CAN_FRAME_UP decoding | `tests/test_protocol.py` | Received bytes decode to correct CANMessage fields |
| FrameReceiver buffering | `tests/test_transport.py` | Partial frames reassembled, multiple frames in stream |
| Heartbeat parsing | `tests/test_transport.py` | Heartbeat bytes → correct MCU model, FW version |
| Capabilities parsing | `tests/test_transport.py` | Capability bitmap → correct feature flags |

### 10.2 Integration Tests (App ↔ Firmware Simulator)

A Python-based firmware simulator (`tools/fw_simulator.py`) that:
- Opens a virtual serial port (via `socat` or `com0com`)
- Responds to all protocol commands with correct ACK/responses
- Generates simulated CAN frames at configurable rate
- Supports all error conditions (bus-off, ADC unavailable, etc.)
- Used for automated testing of the full App→FW→App loop

### 10.3 Hardware-In-the-Loop Tests

| Test | Procedure | Success Criteria |
|------|-----------|-----------------|
| Connect F103 via USART | Flash F103 firmware, connect USB-TTL, click Connect | Heartbeat received, MCU model displayed, capabilities queried |
| Connect F407 via USB CDC | Flash F407 firmware, connect USB, click Connect | Same as above, via USB CDC virtual COM port |
| Send standard CAN frame | Connect, send 0x123 with data "AA BB CC" | ACK received, frame sent on bus |
| Receive CAN frame | Generate CAN traffic on bus (another node) | Frame appears in message table with correct ID, data, timestamp |
| Change baudrate | Connect at 500k, change to 250k | ACK received, subsequent sends succeed |
| Silent mode toggle | Enable silent mode, try sending | Send buttons disabled, CAN mode = listen-only |
| Waveform capture (F407) | Connect F407, open waveform, click Capture | ADC data stream appears in waveform canvas |
| Waveform unavailable (F103) | Connect F103, open waveform, click Capture | "ADC not available" shown |
| Error frame handling | Generate CAN bus error (e.g., disconnect bus) | Error notification in log, error counter increments |
| Disconnect/reconnect | Disconnect, reconnect | Clean state, heartbeat re-sent, new capabilities query |
| Cycle send 100ms | Start cycle at 100ms interval, let run 100 iterations | 100 ACKs received, 0 failures |
| Baudrate auto-detect | Connect device, App auto-detects baudrate | Correct baudrate selected within 5 seconds |

### 10.4 Regression Tests (App UI)

| Test | Procedure |
|------|-----------|
| Demo mode unchanged | Start app without hardware → all UI features functional |
| Language switch | ZH ↔ EN → all labels switch |
| View menu toggles | Toggle each panel → layout reflows correctly |
| Message table collapse | Send multiple same-ID frames → collapse shows one row |
| TX/RX filter | Toggle TX only → only TX frames visible |
| Display filter | Set filter to "show only 0x7DF" → only matching frames |
| Message filter | Set filter to "hide 0x7DF" → 0x7DF blocked from trace |
| Auto-increment | Enable auto-inc, cycle send → data bytes incrementing |
| RTR frame | Check RTR → data entry disabled, auto-inc disabled |
| Copy to clipboard | Select rows, Ctrl+C → paste in notepad |

---

## Appendix A: Protocol Frame Examples

### A.1 App Requests Device Info

```
App → FW:  A5 09 00 01 00 00 XX XX 5A
           │  │     │  │     │     │
           │  │     │  │     │     └── EndMagic 0x5A
           │  │     │  │     └── CRC16 (2 bytes, computed)
           │  │     │  └── Seq = 0x0000
           │  │     └── CMD_GET_INFO = 0x01
           │  └── Length = 0x0009 (9 bytes total)
           └── Magic 0xA5
```

### A.2 Firmware Responds with Device Info

```
FW → App:  A5 55 00 81 00 00 [76-byte device_info_resp_t] XX XX 5A
           │  │     │  │     │
           │  │     │  │     └── Seq = 0x0000 (echoes request)
           │  │     │  └── MSG_INFO_RESPONSE = 0x81
           │  │     └── Length = 0x0055 = 85 (9 + 76)
           │  └── (length hi byte)
           └── Magic 0xA5
```

### A.3 App Sends CAN Frame (ID=0x123, DLC=3, Data=AA BB CC)

```
App → FW:  A5 18 00 34 01 00 [can_send_frame_t: 15 bytes] XX XX 5A
           │  │     │  │     │
           │  │     │  │     └── Seq = 0x0001
           │  │     │  └── CMD_CAN_SEND_FRAME = 0x34
           │  │     └── Length = 0x0018 = 24 (9 + 15)
           │  └── (length hi byte)
           └── Magic 0xA5

where can_send_frame_t:
  23 01 00 00  ← can_id = 0x00000123 (LE)
  03           ← dlc = 3
  00           ← flags = 0 (standard frame, data frame)
  00           ← channel = 0
  AA BB CC 00 00 00 00 00  ← data[8]
```

### A.4 Firmware Receives CAN Frame from Bus (ID=0x7E8, DLC=8)

```
FW → App:  A5 1D 00 90 00 10 [can_frame_up_t: 20 bytes] XX XX 5A
           │  │     │  │     │
           │  │     │  │     └── Seq = 0x1000 (FW's own sequence)
           │  │     │  └── MSG_CAN_FRAME_UP = 0x90
           │  │     └── Length = 0x001D = 29 (9 + 20)
           │  └── (length hi byte)
           └── Magic 0xA5

where can_frame_up_t:
  42 0F 00 00  ← timestamp = 0x00000F42 μs
  E8 07 00 00  ← can_id = 0x000007E8 (LE)
  08           ← dlc = 8
  00           ← flags = 0 (standard, data, not error)
  [8 bytes data]
  00           ← channel = 0
```

### A.5 Firmware Heartbeat (STM32F103C8T6, FW 1.0.0, on USART)

```
FW → App:  A5 2D 00 93 00 00 [device_heartbeat_t: 36 bytes] XX XX 5A
           │  │     │  │     │
           │  │     │  │     └── Seq = 0x0000
           │  │     │  └── MSG_DEVICE_HEARTBEAT = 0x93
           │  │     └── Length = 0x002D = 45 (9 + 36)
           │  └── (length hi byte)
           └── Magic 0xA5

where device_heartbeat_t:
  "STM32F103C8T6\0..."  ← mcu_model[32]
  01                    ← fw_major
  00                    ← fw_minor
  00                    ← fw_patch
  00                    ← comm_interface = COMM_IF_USART
```

---

## Appendix B: Migration from Legacy Protocol

### B.1 What Changes in `core/protocol.py`

| Aspect | Old (LEGACY) | New (CANONICAL) |
|--------|-------------|-----------------|
| Start magic | `0xAA` | `0xA5` |
| End magic | `0x55` | `0x5A` |
| Field order | STX, CMD(1), LEN(2), DATA, CRC16, ETX | Magic(1), LEN(2), CMD(1), SEQ(2), DATA, CRC16, ETX |
| Sequence number | None | 2-byte LE, auto-increment |
| Command codes | Custom values (0x01=CAP_REQ, 0x10=CAN_OPEN, etc.) | Firmware-compatible (§3.2) |
| CRC initial | `0x0000` | `0xFFFF` |
| Payload structs | Unused (raw bytes only) | Packed structs per command (§3.3) |

### B.2 What Changes in `core/transport.py`

| Aspect | Old | New |
|--------|-----|-----|
| Read pattern | Polling `read(size)` | Background thread with `FrameReceiver` byte buffer |
| Device detection | `list_serial_ports()` → pick first CDC | `list_serial_ports()` → try each for heartbeat |
| Write | Raw `write(bytes)` | `write(encode(cmd, payload))` |
| Receive events | Not implemented | `incoming() → list[Frame]`, polled by app |

### B.3 Backward Compatibility

The legacy protocol is NOT preserved. The old `core/protocol.py` `Command` enum and `Frame` dataclass are completely replaced. No backward compatibility shim is needed because the app and firmware were never integrated before this specification.

---

<a name="中文"></a>
# 中文

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [通信协议 — 权威定义](#3-通信协议)
4. [App-固件接口契约](#4-app-固件接口契约)
5. [固件架构](#5-固件架构)
6. [App 架构](#6-app-架构)
7. [集成实施计划](#7-集成实施计划)
8. [数据流与状态机](#8-数据流与状态机)
9. [错误处理策略](#9-错误处理策略)
10. [测试与验证策略](#10-测试与验证策略)
11. [附录 A：协议帧示例](#附录-a协议帧示例)
12. [附录 B：从旧协议迁移](#附录-b从旧协议迁移)

---

## 1. 项目概述

Open-Canoe 是一款开源 CAN 总线分析仪，由两个组件构成：

| 组件 | 技术 | 职责 |
|------|------|------|
| **桌面应用** | Python 3.11+ / tkinter | GUI、用户交互、协议编解码 |
| **硬件探针** | C / STM32 HAL | CAN 总线接口、ADC 采样、协议处理 |

探针通过 USART 或 USB-CDC 使用自定义二进制协议与 App 通信。架构强制严格分离：协议层是共享概念设计，App 永远不依赖固件内部实现，新 MCU 支持永远不需要 App 变更。

### 1.1 设计原则

1. **协议即契约** — 通信协议是唯一接口。只要协议不变，App 和固件可以独立演进。
2. **固件可扩展性** — 新增 MCU 只需新配置目录 + Makefile，无需修改 `inc/`、`src/` 或 App 代码。
3. **App UI 稳定** — 现有 tkinter GUI 布局、控件结构、交互模式全部保留，仅修改底层通信/协议层。
4. **无状态协议** — 每帧独立，不假设会话状态。每个命令对应 ACK/NACK。
5. **优雅降级** — 硬件不可用的功能（ADC、多路 CAN）在连接时查询，相应 UI 元素灰显。

### 1.2 范围

**本规范包含：**
- 权威协议帧格式、命令集和载荷结构
- App 通信层重构方案
- App→固件的所有用户操作命令流
- 固件→App 的推送数据流（CAN 帧、ADC 数据、错误、心跳）
- 错误处理契约
- 测试策略

**不包含：**
- GUI 重设计或新增 UI 功能
- 新 MCU 支持（保留架构，未来扩展）
- 固件驱动逻辑变更（CAN/ADC/COMM 驱动已完成）

---

## 2. 系统架构

参见 English §2 的 ASCII 架构图。

### 2.1 各层职责

| 层 | 所有者 | 变更频率 | 约束 |
|----|--------|---------|------|
| 协议定义 | **本文档** | 极少（版本化） | App 和固件必须一致 |
| App GUI (`gui/`) | App 团队 | 频繁 | 绝不依赖固件 |
| App 协议 (`core/protocol.py`) | App 团队 | 协议版本升级时 | 必须匹配固件 `protocol.h` |
| App 通信 (`core/transport.py`) | App 团队 | 极少 | 实现协议感知接收 |
| 固件 `inc/protocol.h` | 固件团队 | 协议版本升级时 | 必须匹配 App `protocol.py` |
| 固件 `inc/*_api.h` | 固件团队 | 极少 | 硬件无关 |
| 固件 `src/*_driver.c` | 固件团队 | 适配新 MCU 时 | 仅使用配置宏 |
| 固件 `f103/`, `f407/` | 固件团队 | 新增 MCU 时 | CubeMX 文件不得修改 |

---

## 3. 通信协议

**本节是权威协议定义。`core/protocol.py` 和 `firmware/inc/protocol.h` 必须精确实现此定义。**

### 3.1 帧格式

与 English §3.1 完全相同的字节级格式。关键参数：

- 帧头魔术字: `0xA5`
- 帧尾魔术字: `0x5A`
- 长度字段: 2 字节小端，表示总帧长（含自身）
- 命令码: 1 字节
- 序列号: 2 字节小端，单调递增
- 数据域: 0–256 字节
- CRC16: 多项式 `0x1021`，初始值 `0xFFFF`，覆盖帧头+数据

### 3.2 命令码

参见 English §3.2 的完整命令表。

### 3.3 载荷结构

参见 English §3.3 的完整结构体定义。

---

## 4. App-固件接口契约

本节定义每个用户可见操作的精确协议交互序列。完整流程参见 English §4。

### 关键流程

- **连接与发现**：打开串口 → 等待心跳 → 查询能力 → 显示信息
- **CAN 配置**：设置波特率 → 设置模式 → 启停监听
- **发送报文**：App 端本地显示 → 固件发送 → 等待 ACK
- **静默模式**：切换 CAN 模式为 listen-only → 禁用发送按钮
- **波形探测**：查询 ADC 状态 → 配置参数 → 启停采样
- **过滤**：全部在 App 端完成，固件不做软件过滤

---

## 5. 固件架构

目录结构和分层规则与 English §5 一致。

### 5.1 可扩展性保证

新增 MCU 仅需：
1. 创建 `firmware/xxx/`，从 CubeMX 复制文件
2. 创建 `stm32xxx_config.h` + `stm32xxx_hal_conf.h`
3. 创建 `Makefile_xxx`
4. 在 `tools/deploy.py` 注册

**不需要修改 `inc/`、`src/` 或 `tools/` 中的任何文件。**

---

## 6. App 架构

目录结构与 English §6 一致。

### 6.1 App 端协议层（重构目标）

当前 `core/protocol.py` 使用**与固件不同的**帧格式。这是集成工作的核心任务。

**当前（不兼容）：**
- 魔术字 `0xAA/0x55`，字段顺序不同，命令码完全不同

**目标（必须匹配固件）：**
- 魔术字 `0xA5/0x5A`，字段顺序一致，命令码一致

### 6.2 所需变更汇总

| 文件 | 变更 | 原因 |
|------|------|------|
| `core/protocol.py` | **重写** | 匹配固件帧格式 |
| `core/transport.py` | **重构** | 添加后台读取线程、帧缓存、心跳检测 |
| `gui/app.py` | **少量** | 接入连接→心跳→能力查询流程；处理接收的 CAN 帧 |
| `gui/device_bar.py` | **少量** | 显示连接后设备信息 |
| `gui/waveform_window.py` | **少量** | 从通信层获取 ADC 数据 |
| 其他 `gui/*.py` | **无** | UI 控件完全不变 |

---

## 7. 集成实施计划

### 阶段 1：协议对齐（关键路径）
1. 重写 `core/protocol.py`，匹配固件 `protocol.h`
2. 协议往返验证测试

### 阶段 2：通信层重构
1. 添加 `FrameReceiver` 类（字节缓冲→完整帧）
2. 添加后台读取线程
3. 添加心跳设备检测

### 阶段 3：App 集成
1. 重构 `_connect_async()` 流程
2. 添加接收帧处理函数
3. 接入设备栏显示设备信息

### 阶段 4：演示模式保留
无硬件时恢复正常工作。

### 阶段 5：测试
参见 §10。

---

## 8. 数据流与状态机

参见 English §8 的 ASCII 状态机图和数据流图。

---

## 9. 错误处理策略

| 场景 | 固件行为 | App 响应 |
|------|---------|---------|
| 非法命令码 | `MSG_NACK` | 日志记录 |
| 非法参数 | `MSG_ACK` + 错误码 | 日志面板显示错误 |
| CRC 不匹配 | 丢弃帧，重置解析器 | 丢弃帧，累加错误计数 |
| CAN 总线关闭 | `MSG_ERROR_NOTIFY` | 日志红色警告 |
| ADC 不可用 | `MSG_ACK` + `ERR_ADC_NOT_AVAILABLE` | 禁用波形采集 |
| 串口打开失败 | — | 弹窗提示 |
| 心跳超时 | — | 尝试下一波特率/端口 |
| ACK 超时 500ms | — | 日志警告，不自动重试 |

---

## 10. 测试与验证策略

参见 English §10 的完整测试策略表。

### 测试层次

1. **单元测试**：CRC16、编解码往返、帧缓存
2. **集成测试**：Python 固件模拟器，完整 App→FW→App 循环
3. **硬件环回测试**：真实 F103/F407 + ST-Link
4. **回归测试**：App UI 全部功能不受影响

---

## 附录 A：协议帧示例

参见 English Appendix A 的字节级示例。

## 附录 B：从旧协议迁移

| 方面 | 旧（已废弃） | 新（规范） |
|------|-------------|-----------|
| 起始魔术字 | `0xAA` | `0xA5` |
| 结束魔术字 | `0x55` | `0x5A` |
| 字段顺序 | STX, CMD(1), LEN(2), DATA, CRC, ETX | Magic(1), LEN(2), CMD(1), SEQ(2), DATA, CRC, ETX |
| 序列号 | 无 | 2 字节 LE，自动递增 |
| 命令码 | 自定义值 | 固件兼容（§3.2） |
| CRC 初始值 | `0x0000` | `0xFFFF` |
| 载荷结构 | 未使用（仅原始字节） | 打包结构体（§3.3） |

旧协议不保留。不需要向后兼容。

---

**文档结束 / End of Document**
