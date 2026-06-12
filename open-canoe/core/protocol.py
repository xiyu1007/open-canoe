"""Binary frame protocol codec — matches firmware/inc/protocol.h exactly.

Wire format:
  Magic(0xA5) + Length(LE16) + Cmd(1B) + Seq(LE16) + Data(0..256B) + CRC16(LE16) + EndMagic(0x5A)

CRC-CCITT polynomial 0x1021, initial 0xFFFF, over header+data (bytes 0..N-4).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

# ── Protocol Constants ──────────────────────────────────────────────
MAGIC_HEADER = 0xA5
END_MAGIC = 0x5A
FRAME_HEADER_SIZE = 6
FRAME_FOOTER_SIZE = 3
FRAME_OVERHEAD = FRAME_HEADER_SIZE + FRAME_FOOTER_SIZE
FRAME_DATA_MAX = 256
FRAME_TOTAL_MAX = FRAME_OVERHEAD + FRAME_DATA_MAX

# ── Command Codes ────────────────────────────────────────────────────
class Command(IntEnum):
    # App → FW: Info Query (0x00–0x0F)
    GET_INFO = 0x01
    GET_CAPABILITIES = 0x02
    GET_STATUS = 0x03
    GET_ADC_STATUS = 0x04

    # App → FW: Parameter Config (0x10–0x2F)
    CAN_SET_BAUDRATE = 0x10
    CAN_SET_MODE = 0x11
    CAN_SET_FILTER = 0x12
    ADC_SET_SAMPLING = 0x20
    COMM_SET_INTERFACE = 0x28

    # App → FW: Control (0x30–0x4F)
    CAN_START_LISTEN = 0x30
    CAN_STOP_LISTEN = 0x31
    ADC_START_SAMPLE = 0x32
    ADC_STOP_SAMPLE = 0x33
    CAN_SEND_FRAME = 0x34
    SYSTEM_RESET = 0x3F

    # FW → App: Responses (0x80–0x9F)
    INFO_RESPONSE = 0x81
    CAPABILITIES_RESP = 0x82
    STATUS_RESPONSE = 0x83
    ADC_STATUS_RESP = 0x84
    CAN_FRAME_UP = 0x90
    ADC_DATA_UP = 0x91
    ERROR_NOTIFY = 0x92
    DEVICE_HEARTBEAT = 0x93
    ACK = 0xA0
    NACK = 0xA1

    INVALID = 0xFF


# ── CAN Mode Constants ───────────────────────────────────────────────
CAN_MODE_NORMAL = 0x00
CAN_MODE_LISTEN_ONLY = 0x01
CAN_MODE_LOOPBACK = 0x02
CAN_MODE_LOOPBACK_SILENT = 0x03

# ── Error Codes ──────────────────────────────────────────────────────
ERR_NONE = 0x00
ERR_INVALID_CMD = 0x01
ERR_INVALID_PARAM = 0x02
ERR_CRC_MISMATCH = 0x03
ERR_BUFFER_OVERFLOW = 0x04
ERR_TIMEOUT = 0x05
ERR_CAN_BUS_OFF = 0x10
ERR_CAN_ERROR_PASSIVE = 0x11
ERR_CAN_TX_FAILED = 0x12
ERR_CAN_RX_OVERRUN = 0x13
ERR_ADC_NOT_AVAILABLE = 0x20
ERR_ADC_OVERRUN = 0x21
ERR_COMM_TX_FAILED = 0x30
ERR_COMM_RX_OVERRUN = 0x31
ERR_NOT_INITIALIZED = 0x40
ERR_ALREADY_RUNNING = 0x41
ERR_HARDWARE_FAULT = 0xFF

# ── Capability Bits ──────────────────────────────────────────────────
CAP_ADC = 1 << 0
CAP_USB_CDC = 1 << 1
CAP_MULTI_CAN = 1 << 2
CAP_TIMESTAMP_US = 1 << 3

# ── Error Messages ───────────────────────────────────────────────────
ERROR_MESSAGES: dict[int, str] = {
    ERR_NONE: "Success",
    ERR_INVALID_CMD: "Invalid command",
    ERR_INVALID_PARAM: "Invalid parameter",
    ERR_CRC_MISMATCH: "CRC mismatch",
    ERR_BUFFER_OVERFLOW: "Buffer overflow",
    ERR_TIMEOUT: "Timeout",
    ERR_CAN_BUS_OFF: "CAN bus-off",
    ERR_CAN_ERROR_PASSIVE: "CAN error-passive",
    ERR_CAN_TX_FAILED: "CAN TX failed",
    ERR_CAN_RX_OVERRUN: "CAN RX overrun",
    ERR_ADC_NOT_AVAILABLE: "ADC not available",
    ERR_ADC_OVERRUN: "ADC overrun",
    ERR_COMM_TX_FAILED: "Comm TX failed",
    ERR_COMM_RX_OVERRUN: "Comm RX overrun",
    ERR_NOT_INITIALIZED: "Not initialized",
    ERR_ALREADY_RUNNING: "Already running",
    ERR_HARDWARE_FAULT: "Hardware fault",
}

# ── CRC16 (CRC-CCITT) ────────────────────────────────────────────────
_CRC_TABLE: list[int] = []


def _make_crc_table() -> list[int]:
    t = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        t.append(crc & 0xFFFF)
    return t


def crc16(data: bytes) -> int:
    """CRC-CCITT, polynomial 0x1021, initial 0xFFFF."""
    if not _CRC_TABLE:
        _CRC_TABLE.extend(_make_crc_table())
    crc = 0xFFFF
    for b in data:
        crc = ((crc << 8) ^ _CRC_TABLE[((crc >> 8) ^ b) & 0xFF]) & 0xFFFF
    return crc


# ── Frame ────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Frame:
    command: Command
    seq: int = 0
    payload: bytes = b""


# ── Sequence Counter ─────────────────────────────────────────────────
_seq_counter: int = 0


def next_seq() -> int:
    global _seq_counter
    s = _seq_counter
    _seq_counter = (_seq_counter + 1) & 0xFFFF
    return s


def reset_seq() -> None:
    global _seq_counter
    _seq_counter = 0


# ── Encode / Decode ──────────────────────────────────────────────────


def encode(command: Command, payload: bytes = b"") -> bytes:
    """Encode a command + payload into a wire-format frame."""
    if len(payload) > FRAME_DATA_MAX:
        raise ValueError(f"payload too large: {len(payload)} > {FRAME_DATA_MAX}")
    seq = next_seq()
    total_len = FRAME_OVERHEAD + len(payload)
    header_body = struct.pack(
        "<B H B H",
        MAGIC_HEADER,
        total_len,
        int(command),
        seq,
    ) + payload
    crc_val = crc16(header_body)
    return header_body + struct.pack("<H B", crc_val, END_MAGIC)


def encode_with_seq(command: Command, seq: int, payload: bytes = b"") -> bytes:
    """Encode with explicit sequence number (for responses)."""
    if len(payload) > FRAME_DATA_MAX:
        raise ValueError(f"payload too large: {len(payload)} > {FRAME_DATA_MAX}")
    total_len = FRAME_OVERHEAD + len(payload)
    header_body = struct.pack(
        "<B H B H",
        MAGIC_HEADER,
        total_len,
        int(command),
        seq,
    ) + payload
    crc_val = crc16(header_body)
    return header_body + struct.pack("<H B", crc_val, END_MAGIC)


def decode(data: bytes) -> list[Frame]:
    """Decode a chunk of bytes, returning all valid complete frames found."""
    frames: list[Frame] = []
    buf = bytearray()
    buf.extend(data)

    while len(buf) >= FRAME_OVERHEAD:
        # Find magic header
        if buf[0] != MAGIC_HEADER:
            del buf[0]
            continue

        if len(buf) < 3:
            break

        total_len = buf[1] | (buf[2] << 8)
        if total_len < FRAME_OVERHEAD or total_len > FRAME_TOTAL_MAX:
            del buf[0]
            continue

        if len(buf) < total_len:
            break  # Incomplete frame, wait for more data

        # Check end magic
        if buf[total_len - 1] != END_MAGIC:
            del buf[0]
            continue

        payload_len = total_len - FRAME_OVERHEAD

        # Validate CRC: over header + data (bytes 0 to total_len-3)
        computed = crc16(bytes(buf[: FRAME_HEADER_SIZE + payload_len]))
        crc_offset = FRAME_HEADER_SIZE + payload_len
        received = buf[crc_offset] | (buf[crc_offset + 1] << 8)

        if computed != received:
            del buf[0]
            continue

        # Extract fields
        cmd = Command(buf[3])
        seq = buf[4] | (buf[5] << 8)
        payload = bytes(buf[FRAME_HEADER_SIZE : FRAME_HEADER_SIZE + payload_len])

        frames.append(Frame(command=cmd, seq=seq, payload=payload))
        del buf[:total_len]

    return frames


# ── Payload Encode / Decode Functions ─────────────────────────────────


def pack_can_send_frame(
    can_id: int,
    dlc: int,
    is_extended: bool = False,
    is_remote: bool = False,
    channel: int = 0,
    data: bytes = b"",
) -> bytes:
    """Pack a can_send_frame_t payload (CMD_CAN_SEND_FRAME)."""
    flags = 0
    if is_extended:
        flags |= 0x01
    if is_remote:
        flags |= 0x02
    payload = struct.pack("<I B B B", can_id, dlc, flags, channel)
    payload += data.ljust(8, b"\x00")[:8]
    return payload


def unpack_can_frame_up(payload: bytes) -> dict:
    """Unpack a can_frame_up_t payload (MSG_CAN_FRAME_UP)."""
    timestamp, can_id, dlc, flags, raw_data, channel = struct.unpack(
        "<I I B B 8s B", payload[:20]
    )
    return {
        "timestamp_us": timestamp,
        "arbitration_id": can_id,
        "dlc": dlc,
        "is_extended": bool(flags & 0x01),
        "is_remote": bool(flags & 0x02),
        "is_error": bool(flags & 0x04),
        "data": raw_data[:dlc] if dlc <= 8 else raw_data[:8],
        "channel": channel,
    }


def pack_can_set_baudrate(baudrate: int, channel: int = 0) -> bytes:
    """Pack a can_set_baudrate_t payload."""
    return struct.pack("<I B", baudrate, channel)


def pack_can_set_mode(mode: int, channel: int = 0) -> bytes:
    """Pack a can_set_mode_t payload."""
    return struct.pack("<B B", channel, mode)


def pack_can_set_filter(
    channel: int = 0,
    filter_index: int = 0,
    filter_mode: int = 0,
    filter_scale: int = 1,
    id_high: int = 0,
    id_low: int = 0,
    mask_high: int = 0,
    mask_low: int = 0,
) -> bytes:
    """Pack a can_set_filter_t payload."""
    return struct.pack(
        "<B B B B I I I I",
        channel, filter_index, filter_mode, filter_scale,
        id_high, id_low, mask_high, mask_low,
    )


def unpack_device_info(payload: bytes) -> dict:
    """Unpack a device_info_resp_t payload."""
    fw_major, fw_minor, fw_patch, reserved, proto_ver = struct.unpack(
        "<B B B B H", payload[:6]
    )
    mcu_model = payload[6:38].decode("utf-8", errors="replace").strip("\x00")
    fw_desc = payload[38:70].decode("utf-8", errors="replace").strip("\x00")
    device_serial = struct.unpack("<I", payload[70:74])[0]
    return {
        "fw_version": f"{fw_major}.{fw_minor}.{fw_patch}",
        "protocol_version": f"{(proto_ver >> 8) & 0xFF}.{proto_ver & 0xFF}",
        "mcu_model": mcu_model,
        "fw_description": fw_desc,
        "device_serial": f"0x{device_serial:08X}",
    }


def unpack_capabilities(payload: bytes) -> dict:
    """Unpack a capabilities_resp_t payload."""
    bits, can_count, max_rate, res, max_baud = struct.unpack(
        "<I B I B H", payload[:12]
    )
    return {
        "capability_bits": bits,
        "has_adc": bool(bits & CAP_ADC),
        "has_usb_cdc": bool(bits & CAP_USB_CDC),
        "has_multi_can": bool(bits & CAP_MULTI_CAN),
        "has_timestamp_us": bool(bits & CAP_TIMESTAMP_US),
        "can_channel_count": can_count,
        "max_adc_sample_rate": max_rate,
        "adc_resolution": res,
        "max_can_baudrate_kbps": max_baud,
    }


def unpack_heartbeat(payload: bytes) -> dict:
    """Unpack a device_heartbeat_t payload."""
    mcu_model = payload[:32].decode("utf-8", errors="replace").strip("\x00")
    fw_major, fw_minor, fw_patch, comm_if = struct.unpack("<B B B B", payload[32:36])
    return {
        "mcu_model": mcu_model,
        "fw_version": f"{fw_major}.{fw_minor}.{fw_patch}",
        "comm_interface": "USART" if comm_if == 0 else "USB_CDC",
    }


def unpack_status(payload: bytes) -> dict:
    """Unpack a status_resp_t payload."""
    can_listening, adc_sampling, comm_if, ch_active, uptime = struct.unpack(
        "<B B B B I", payload[:8]
    )
    return {
        "can_listening": bool(can_listening),
        "adc_sampling": bool(adc_sampling),
        "comm_interface": "USART" if comm_if == 0 else "USB_CDC",
        "can_channels_active": ch_active,
        "uptime_ms": uptime,
    }


def unpack_ack(payload: bytes) -> dict:
    """Unpack an ack_resp_t payload."""
    ack_cmd = payload[0]
    error_code = payload[1] if len(payload) > 1 else 0
    return {"ack_cmd": ack_cmd, "error_code": error_code}


def unpack_error_notify(payload: bytes) -> dict:
    """Unpack an error_notify_t payload."""
    error_code, source, flags, timestamp = struct.unpack("<B B H I", payload[:8])
    source_names = {0: "CAN", 1: "ADC", 2: "COMM", 3: "SYSTEM"}
    return {
        "error_code": error_code,
        "error_name": ERROR_MESSAGES.get(error_code, f"Unknown(0x{error_code:02X})"),
        "source": source_names.get(source, f"Unknown({source})"),
        "error_flags": flags,
        "timestamp": timestamp,
    }
