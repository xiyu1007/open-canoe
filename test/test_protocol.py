#!/usr/bin/env python3
"""
Open-Canoe Protocol Unit Tests

Tests the protocol codec independently of hardware.
Run: cd open-canoe && uv run python ../test/test_protocol.py
"""

import sys, os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "open-canoe"))

from core.protocol import (
    Command,
    encode,
    decode,
    crc16,
    Frame,
    pack_can_send_frame,
    unpack_can_frame_up,
    pack_can_set_baudrate,
    pack_can_set_mode,
    unpack_device_info,
    unpack_capabilities,
    unpack_heartbeat,
    unpack_ack,
    unpack_error_notify,
    CAN_MODE_NORMAL,
    CAN_MODE_LOOPBACK,
    MAGIC_HEADER,
    END_MAGIC,
    FRAME_HEADER_SIZE,
    FRAME_OVERHEAD,
    reset_seq,
    next_seq,
)

PASS = 0
FAIL = 0


def t(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def main():
    global PASS, FAIL
    print("Open-Canoe Protocol Unit Tests")
    print("=" * 50)

    # 1. CRC16 known vectors
    print("\n-- CRC16 --")
    t("CRC16 empty", crc16(b"") == 0xFFFF)
    t("CRC16 '123456789'", crc16(b"123456789") != crc16(b""))
    t("CRC16 deterministic", crc16(b"test") == crc16(b"test"))

    # 2. Encode/Decode round-trip
    print("\n-- Encode/Decode --")
    reset_seq()
    frame = encode(Command.GET_INFO)
    t("GET_INFO encode", len(frame) == 9)
    t("GET_INFO magic", frame[0] == MAGIC_HEADER)
    t("GET_INFO end", frame[-1] == END_MAGIC)

    frames = decode(frame)
    t("GET_INFO decode 1 frame", len(frames) == 1)
    t("GET_INFO cmd match", frames[0].command == Command.GET_INFO)
    t("GET_INFO seq", frames[0].seq == 0)

    # 3. CAN_SEND_FRAME encode
    print("\n-- CAN_SEND_FRAME --")
    payload = pack_can_send_frame(0x123, 3, data=bytes([0xAA, 0xBB, 0xCC]))
    t("pack_can_send_frame len", len(payload) == 15)
    t("pack_can_send_frame ID", payload[0] == 0x23 and payload[1] == 0x01)
    t("pack_can_send_frame DLC", payload[4] == 3)

    frame = encode(Command.CAN_SEND_FRAME, payload)
    frames = decode(frame)
    t("CAN_SEND_FRAME round-trip", len(frames) == 1 and frames[0].command == Command.CAN_SEND_FRAME)

    # 4. CAN_FRAME_UP decode (simulate firmware response)
    print("\n-- CAN_FRAME_UP unpack --")
    # Build a synthetic can_frame_up_t
    import struct
    payload_rx = struct.pack(
        "<I I B B 8s B",
        0x12345,      # timestamp
        0x7E8,        # can_id
        8,            # dlc
        0x01,         # flags (EXT)
        bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88]),
        0,            # channel
    )
    d = unpack_can_frame_up(payload_rx)
    t("unpack timestamp", d["timestamp_us"] == 0x12345)
    t("unpack can_id", d["arbitration_id"] == 0x7E8)
    t("unpack dlc", d["dlc"] == 8)
    t("unpack ext", d["is_extended"] == True)
    t("unpack data[0]", d["data"][0] == 0x11)
    t("unpack data[7]", d["data"][7] == 0x88)

    # 5. Multiple frames in stream
    print("\n-- Multi-Frame Decode --")
    reset_seq()
    f1 = encode(Command.GET_INFO)
    f2 = encode(Command.GET_CAPABILITIES)
    combined = f1 + f2
    frames = decode(combined)
    t("decode 2 frames", len(frames) == 2)
    t("frame 1 cmd", frames[0].command == Command.GET_INFO)
    t("frame 2 cmd", frames[1].command == Command.GET_CAPABILITIES)

    # 6. Partial frame (incomplete)
    print("\n-- Partial Frame Handling --")
    f3 = encode(Command.CAN_SET_BAUDRATE, pack_can_set_baudrate(500000, 0))
    partial = f3[:5]  # Only first 5 bytes
    frames = decode(partial)
    t("partial returns empty", len(frames) == 0)

    # 7. Pack/unpack helpers
    print("\n-- Payload Helpers --")
    t("pack_can_set_baudrate", len(pack_can_set_baudrate(500000, 0)) == 5)
    t("pack_can_set_mode", len(pack_can_set_mode(CAN_MODE_LOOPBACK, 0)) == 2)

    # 8. Sequence number
    print("\n-- Sequence Numbers --")
    reset_seq()
    t("seq starts at 0", next_seq() == 0)
    t("seq increments", next_seq() == 1)
    t("seq continues", next_seq() == 2)

    # 9. Extended frame flags
    print("\n-- Extended Frame Pack --")
    ext_payload = pack_can_send_frame(0x18DAF110, 4, is_extended=True,
                                       data=bytes([1, 2, 3, 4]))
    t("ext flags byte", ext_payload[5] == 0x01)  # IDE bit set

    # 10. Remote frame flags
    print("\n-- Remote Frame Pack --")
    rtr_payload = pack_can_send_frame(0x456, 3, is_remote=True)
    t("rtr flags byte", rtr_payload[5] == 0x02)  # RTR bit set

    # Summary
    print("\n" + "=" * 50)
    print(f"Results: {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"{FAIL} TEST(S) FAILED")
    return FAIL == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
