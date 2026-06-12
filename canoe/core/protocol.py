"""Binary frame protocol codec — CRC-16/XMODEM.

Wire format: STX(0xAA) | CMD(1B) | LEN(2B LE) | PAYLOAD(0..255B) | CRC16(2B LE) | ETX(0x55)
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

_STX = 0xAA
_ETX = 0x55


class Command(IntEnum):
    CAPABILITIES_REQ = 0x01
    CAN_OPEN = 0x10
    CAN_CLOSE = 0x11
    CAN_SEND = 0x12
    CAN_SET_FILTER = 0x13
    CAN_SET_BITRATE = 0x14
    WAVE_START = 0x20
    WAVE_STOP = 0x21
    RESET = 0x7F
    CAPABILITIES_RESP = 0x81
    CAN_MESSAGE_RX = 0x90
    CAN_ERROR = 0x91
    CAN_BUS_STATUS = 0x92
    WAVE_SAMPLE = 0xA0
    WAVE_DONE = 0xA1
    LOG_MESSAGE = 0xF0


@dataclass(frozen=True, slots=True)
class Frame:
    command: Command
    payload: bytes = b""
    crc: int = 0


# CRC-16/XMODEM lookup table
_CRC_TABLE: list[int] = []


def _make_crc_table() -> list[int]:
    t: list[int] = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        t.append(crc & 0xFFFF)
    return t


def _crc16(data: bytes) -> int:
    if not _CRC_TABLE:
        _CRC_TABLE.extend(_make_crc_table())
    crc = 0
    for b in data:
        crc = ((crc << 8) ^ _CRC_TABLE[((crc >> 8) ^ b) & 0xFF]) & 0xFFFF
    return crc


def encode(command: Command, payload: bytes = b"") -> bytes:
    if len(payload) > 65535:
        raise ValueError("payload too large")
    header_body = bytes([command]) + struct.pack("<H", len(payload)) + payload
    crc = _crc16(header_body)
    return bytes([_STX]) + header_body + struct.pack("<H", crc) + bytes([_ETX])


def decode(data: bytes) -> list[Frame]:
    """Decode a chunk of bytes, returning all valid complete frames found."""
    frames: list[Frame] = []
    buf = bytearray()

    for b in data:
        buf.append(b)
        while len(buf) >= 7:
            if buf[0] != _STX:
                del buf[0]
                continue
            payload_len = buf[2] | (buf[3] << 8)
            frame_len = 7 + payload_len
            if len(buf) < frame_len:
                break
            if buf[frame_len - 1] != _ETX:
                del buf[0]
                continue
            header_body = buf[1 : 4 + payload_len]
            crc_rx = buf[4 + payload_len] | (buf[5 + payload_len] << 8)
            if _crc16(header_body) != crc_rx:
                del buf[0]
                continue
            try:
                cmd = Command(buf[1])
            except ValueError:
                del buf[0]
                continue
            frames.append(Frame(
                command=cmd,
                payload=bytes(buf[4 : 4 + payload_len]),
                crc=crc_rx,
            ))
            del buf[:frame_len]

    return frames
