"""
Frame encode/decode with CRC16-CCITT (polynomial 0x1021, initial 0xFFFF).
Matches hardware/src/protocol_handler.c exactly.
"""
import struct
from .protocol_defs import (
    PROTOCOL_MAGIC_HEADER, PROTOCOL_END_MAGIC,
    PROTOCOL_FRAME_HEADER_SIZE, PROTOCOL_FRAME_FOOTER_SIZE,
    PROTOCOL_FRAME_OVERHEAD, PROTOCOL_FRAME_DATA_MAX,
)

_CRC16_TABLE = None


def _make_crc16_table():
    global _CRC16_TABLE
    if _CRC16_TABLE is not None:
        return _CRC16_TABLE
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
        table.append(crc)
    _CRC16_TABLE = table
    return table


def crc16(data: bytes, initial: int = 0xFFFF) -> int:
    """CRC16-CCITT with table lookup."""
    table = _make_crc16_table()
    crc = initial
    for b in data:
        crc = ((crc << 8) ^ table[((crc >> 8) ^ b) & 0xFF]) & 0xFFFF
    return crc


class DecodeResult:
    def __init__(self, ok: bool, cmd: int = 0, seq: int = 0,
                 data: bytes = b"", error: str = ""):
        self.ok = ok
        self.cmd = cmd
        self.seq = seq
        self.data = data
        self.error = error


class FrameCodec:
    """Stateless frame encoder/decoder."""

    @staticmethod
    def encode(cmd: int, seq: int, data: bytes = b"") -> bytes:
        """Build a complete binary frame ready to send over serial."""
        if len(data) > PROTOCOL_FRAME_DATA_MAX:
            raise ValueError(f"Data too long: {len(data)} > {PROTOCOL_FRAME_DATA_MAX}")
        total_len = PROTOCOL_FRAME_OVERHEAD + len(data)
        # Header: magic(1) + length(2 LE) + cmd(1) + seq(2 LE)
        header = struct.pack("<B H B H", PROTOCOL_MAGIC_HEADER, total_len, cmd, seq)
        # CRC16 over header + data
        crc = crc16(header + data)
        footer = struct.pack("<H B", crc, PROTOCOL_END_MAGIC)
        return header + data + footer

    @staticmethod
    def decode_one(raw: bytes) -> DecodeResult:
        """Try to decode one frame from raw bytes. Returns DecodeResult.
        If the frame is valid but we consumed only part of raw,
        the remaining bytes are NOT returned — caller manages the buffer.
        """
        if len(raw) < PROTOCOL_FRAME_OVERHEAD:
            return DecodeResult(False, error="Too short for header")

        # Find magic
        idx = raw.find(bytes([PROTOCOL_MAGIC_HEADER]))
        if idx < 0:
            return DecodeResult(False, error="No magic byte found")
        if idx > 0:
            return DecodeResult(False, error=f"Skipped {idx} bytes before magic")

        if len(raw) < 4:
            return DecodeResult(False, error="Need at least 4 bytes for length field")

        total_len = struct.unpack_from("<H", raw, 1)[0]
        if total_len < PROTOCOL_FRAME_OVERHEAD:
            return DecodeResult(False, error=f"Invalid length: {total_len}")
        if total_len > PROTOCOL_FRAME_OVERHEAD + PROTOCOL_FRAME_DATA_MAX:
            return DecodeResult(False, error=f"Length too large: {total_len}")

        if len(raw) < total_len:
            return DecodeResult(False, error=f"Need {total_len} bytes, have {len(raw)}")

        frame = raw[:total_len]
        # Check end magic
        if frame[-1] != PROTOCOL_END_MAGIC:
            return DecodeResult(False, error="End magic mismatch")

        # Verify CRC16 (over header + data, not including footer)
        body = frame[:-PROTOCOL_FRAME_FOOTER_SIZE]
        expected_crc = struct.unpack_from("<H", frame, len(body))[0]
        actual_crc = crc16(body)
        if expected_crc != actual_crc:
            return DecodeResult(False, error=f"CRC mismatch: expected 0x{expected_crc:04X}, got 0x{actual_crc:04X}")

        cmd = frame[3]
        seq = struct.unpack_from("<H", frame, 4)[0]
        data_len = total_len - PROTOCOL_FRAME_OVERHEAD
        data = frame[PROTOCOL_FRAME_HEADER_SIZE:PROTOCOL_FRAME_HEADER_SIZE + data_len]

        return DecodeResult(True, cmd=cmd, seq=seq, data=data)

    @staticmethod
    def feed_and_decode(buffer: bytearray, new_data: bytes):
        """Feed new bytes into buffer, yield all complete DecodeResults found.
        Incomplete/skipped bytes remain in buffer. Caller should do:
            buffer = bytearray()
            for result in FrameCodec.feed_and_decode(buffer, incoming):
                handle(result)
        """
        buffer.extend(new_data)
        while True:
            if len(buffer) < PROTOCOL_FRAME_OVERHEAD:
                break
            # Find magic
            idx = buffer.find(bytes([PROTOCOL_MAGIC_HEADER]))
            if idx < 0:
                buffer.clear()
                break
            if idx > 0:
                del buffer[:idx]
                continue  # re-check after skip

            if len(buffer) < 4:
                break

            total_len = struct.unpack_from("<H", memoryview(buffer), 1)[0]
            if total_len < PROTOCOL_FRAME_OVERHEAD or total_len > PROTOCOL_FRAME_OVERHEAD + PROTOCOL_FRAME_DATA_MAX:
                del buffer[:1]  # skip the bogus magic, try again
                continue

            if len(buffer) < total_len:
                break  # wait for more data

            frame = bytes(buffer[:total_len])
            del buffer[:total_len]

            result = FrameCodec.decode_one(frame)
            yield result
