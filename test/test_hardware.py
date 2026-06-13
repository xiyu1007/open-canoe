#!/usr/bin/env python3
"""
Open-Canoe Hardware Test Suite

Tests the complete App-Firmware protocol interaction with a real STM32 probe.
Requires: pyserial, and a flashed CAN probe connected via USART/USB-CDC.

Usage:
    python test/test_hardware.py COM7              # Test specific port
    python test/test_hardware.py COM7 --baud 921600 # With custom baudrate
    python test/test_hardware.py --scan             # Scan all ports for devices
    python test/test_hardware.py COM7 --loopback    # Loopback mode test (no external CAN bus needed)

Prerequisites:
    cd open-canoe
    uv run python ../test/test_hardware.py COM7
"""

from __future__ import annotations

import sys
import os
import time
import argparse
import traceback

# Add open-canoe to path for imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.join(SCRIPT_DIR, "..", "open-canoe")
sys.path.insert(0, PROJECT_DIR)

from core.transport import (
    SerialTransport,
    TransportError,
    list_serial_ports,
    _try_heartbeat,
    detect_and_connect,
)
from core.protocol import (
    Command,
    Frame,
    encode,
    decode,
    pack_can_send_frame,
    pack_can_set_baudrate,
    pack_can_set_mode,
    unpack_can_frame_up,
    unpack_device_info,
    unpack_capabilities,
    unpack_heartbeat,
    unpack_status,
    unpack_ack,
    unpack_error_notify,
    CAN_MODE_NORMAL,
    CAN_MODE_LISTEN_ONLY,
    CAN_MODE_LOOPBACK,
    CAN_MODE_LOOPBACK_SILENT,
    ERR_NONE,
    ERROR_MESSAGES,
)

# ── Test Helpers ──────────────────────────────────────────────────────

PASS = 0
FAIL = 1
total = 0
passed = 0
failed = 0


def test(name: str):
    global total
    total += 1
    print(f"\n  [{total}] {name}...", end=" ")
    return name


def ok():
    global passed
    passed += 1
    print("PASS")


def fail(reason: str = ""):
    global failed
    failed += 1
    print(f"FAIL{': ' + reason if reason else ''}")


def expect_frame(tr: SerialTransport, cmd: Command, timeout: float = 2.0) -> Frame | None:
    """Wait for a specific command frame. Returns None on timeout.
    Non-matching frames are stashed for subsequent calls.
    """
    global _stash
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # Check stash first
        for i, f in enumerate(_stash):
            if f.command == cmd:
                return _stash.pop(i)
        # Collect all available frames, stashing non-matching ones
        frames = tr.incoming()
        matched = None
        for f in frames:
            if f.command == cmd and matched is None:
                matched = f
            else:
                _stash.append(f)
        if matched is not None:
            return matched
        time.sleep(0.02)
    return None


def expect_ack(tr: SerialTransport, timeout: float = 1.0) -> dict | None:
    """Wait for an ACK frame and return the parsed ack dict."""
    f = expect_frame(tr, Command.ACK, timeout)
    if f is None:
        return None
    try:
        return unpack_ack(f.payload)
    except Exception:
        return None

# Stash for non-matching frames between expect_frame calls
_stash: list = []


# ── Port Scanning ─────────────────────────────────────────────────────


def cmd_scan():
    """Scan all ports for CAN probes."""
    print("=" * 60)
    print("  Open-Canoe Device Scanner")
    print("=" * 60)
    ports = list_serial_ports()
    if not ports:
        print("\n  No serial ports found.")
        return

    print(f"\n  Found {len(ports)} port(s):")
    for p in ports:
        print(f"    {p.port:10s}  {p.transport_type:8s}  {p.description}")

    print("\n  Scanning for CAN probes...")
    found = False
    for p in ports:
        for br in [115200, 921600, 460800]:
            hb = _try_heartbeat(p.port, br, timeout=1.0)
            if hb:
                found = True
                print(f"\n  Found CAN probe!")
                print(f"    Port:      {p.port}")
                print(f"    Baudrate:  {br}")
                print(f"    MCU:       {hb.get('mcu_model', '?')}")
                print(f"    FW:        v{hb.get('fw_version', '?')}")
                print(f"    Interface: {hb.get('comm_interface', '?')}")
                break
    if not found:
        print("\n  No CAN probes detected.")


# ── Full Hardware Test ────────────────────────────────────────────────


def run_tests(port: str, baudrate: int = 115200):
    global total, passed, failed, _stash
    total = passed = failed = 0
    _stash.clear()

    print("=" * 60)
    print(f"  Open-Canoe Hardware Test Suite")
    print(f"  Port: {port}  Baudrate: {baudrate}")
    print("=" * 60)

    tr = SerialTransport(port=port, baudrate=baudrate)

    # ── Test 1: Connect ──────────────────────────────────────────
    test("Open serial port")
    try:
        tr.connect()
        ok()
    except Exception as e:
        fail(str(e))
        print("\n  Cannot continue without connection.")
        return

    time.sleep(0.3)

    # ── Test 2: Heartbeat Detection ──────────────────────────────
    test("Detect device heartbeat")
    hb_frame = expect_frame(tr, Command.DEVICE_HEARTBEAT, timeout=3.0)
    if hb_frame is None:
        # Heartbeat may have been sent before we opened the port.
        # Fall back to GET_INFO to confirm device presence.
        print("(heartbeat already sent, using GET_INFO)")
        tr.write(encode(Command.GET_INFO))
        info_f = expect_frame(tr, Command.INFO_RESPONSE, timeout=2.0)
        if info_f is None:
            fail("No heartbeat or INFO_RESPONSE — device not responding")
            tr.disconnect()
            return
        try:
            info = unpack_device_info(info_f.payload)
            ok()
            print(f"         FW: v{info['fw_version']}  Proto: v{info['protocol_version']}")
            hb = {"mcu_model": info["mcu_model"], "fw_version": info["fw_version"],
                  "comm_interface": "USART"}
        except Exception as e:
            fail(f"Parse error: {e}")
            tr.disconnect()
            return
    else:
        try:
            hb = unpack_heartbeat(hb_frame.payload)
            ok()
            print(f"         MCU: {hb['mcu_model']}  FW: v{hb['fw_version']}  IF: {hb['comm_interface']}")
        except Exception as e:
            fail(f"Parse error: {e}")
            tr.disconnect()
            return

    # ── Test 3: Get Device Info ──────────────────────────────────
    test("Get device info")
    tr.write(encode(Command.GET_INFO))
    info_f = expect_frame(tr, Command.INFO_RESPONSE, timeout=2.0)
    if info_f is None:
        fail("No INFO_RESPONSE")
    else:
        info = unpack_device_info(info_f.payload)
        ok()
        print(f"         SN: {info['device_serial']}  Proto: v{info['protocol_version']}")

    # ── Test 4: Get Capabilities ─────────────────────────────────
    test("Get device capabilities")
    tr.write(encode(Command.GET_CAPABILITIES))
    caps_f = expect_frame(tr, Command.CAPABILITIES_RESP, timeout=2.0)
    if caps_f is None:
        fail("No CAPABILITIES_RESP")
    else:
        caps = unpack_capabilities(caps_f.payload)
        ok()
        print(f"         ADC={caps['has_adc']}  USB_CDC={caps['has_usb_cdc']}  "
              f"CAN={caps['can_channel_count']}ch  Timestamp={caps['has_timestamp_us']}")

    # ── Test 5: Get Status ───────────────────────────────────────
    test("Get device status")
    tr.write(encode(Command.GET_STATUS))
    status_f = expect_frame(tr, Command.STATUS_RESPONSE, timeout=2.0)
    if status_f is None:
        fail("No STATUS_RESPONSE")
    else:
        st = unpack_status(status_f.payload)
        ok()
        print(f"         CAN listening={st['can_listening']}  "
              f"ADC sampling={st['adc_sampling']}  Uptime={st['uptime_ms']}ms")

    # ── Test 6: Configure CAN Baudrate ───────────────────────────
    test("Set CAN baudrate 500k")
    tr.write(encode(Command.CAN_SET_BAUDRATE, pack_can_set_baudrate(500000, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
    else:
        ok()

    # ── Test 7: Set CAN Normal Mode ──────────────────────────────
    test("Set CAN normal mode")
    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(CAN_MODE_NORMAL, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
    else:
        ok()

    # ── Test 8: Start CAN Listening ──────────────────────────────
    test("Start CAN listening")
    tr.write(encode(Command.CAN_START_LISTEN))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
    else:
        ok()

    time.sleep(0.2)

    # ── Test 9: Set Loopback Mode ────────────────────────────────
    test("Set CAN loopback mode")
    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(CAN_MODE_LOOPBACK, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
    else:
        ok()

    # ── Test 10: Send CAN Frame & Receive Loopback ───────────────
    test("Send CAN frame (loopback receive)")
    can_id = 0x123
    test_data = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11])
    payload = pack_can_send_frame(can_id=can_id, dlc=8, is_extended=False, data=test_data)
    tr.write(encode(Command.CAN_SEND_FRAME, payload))

    # Wait for software loopback (sent even if HW TX fails)
    rx_f = expect_frame(tr, Command.CAN_FRAME_UP, timeout=2.0)
    if rx_f is None:
        fail("No loopback CAN frame received")
    else:
        d = unpack_can_frame_up(rx_f.payload)
        ok()
        print(f"         RX ID=0x{d['arbitration_id']:X} DLC={d['dlc']} "
              f"data={' '.join(f'{b:02X}' for b in d['data'])}")

    # ── Test 11: Send Extended Frame ─────────────────────────────
    test("Send extended CAN frame (loopback)")
    can_id_ext = 0x18DAF110
    payload = pack_can_send_frame(can_id=can_id_ext, dlc=4, is_extended=True,
                                   data=bytes([0x01, 0x02, 0x03, 0x04]))
    tr.write(encode(Command.CAN_SEND_FRAME, payload))
    rx_f = expect_frame(tr, Command.CAN_FRAME_UP, timeout=2.0)
    if rx_f is None:
        fail("No loopback extended frame received")
    else:
        d = unpack_can_frame_up(rx_f.payload)
        ok()
        print(f"         RX ID=0x{d['arbitration_id']:X} EXT={d['is_extended']} DLC={d['dlc']}")

    # ── Test 12: Send Remote Frame ───────────────────────────────
    test("Send remote frame (loopback)")
    payload = pack_can_send_frame(can_id=0x456, dlc=3, is_remote=True)
    tr.write(encode(Command.CAN_SEND_FRAME, payload))
    rx_f = expect_frame(tr, Command.CAN_FRAME_UP, timeout=2.0)
    if rx_f is None:
        fail("No loopback remote frame received")
    else:
        d = unpack_can_frame_up(rx_f.payload)
        ok()
        print(f"         RX RTR={d['is_remote']} DLC={d['dlc']}")

    # ── Test 13: Switch to Listen-Only Mode ──────────────────────
    test("Set CAN listen-only mode")
    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(CAN_MODE_LISTEN_ONLY, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
    else:
        ok()

    # ── Test 14: Normal Mode Again ───────────────────────────────
    test("Set CAN normal mode")
    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(CAN_MODE_NORMAL, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
    else:
        ok()

    # ── Test 15: Multi-Frame Burst ───────────────────────────────
    test("Multi-frame burst (5 frames, loopback)")
    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(CAN_MODE_LOOPBACK, 0)))
    expect_ack(tr, timeout=0.5)
    received = 0
    for i in range(5):
        payload = pack_can_send_frame(can_id=0x100 + i, dlc=2,
                                       data=bytes([i, 0xFF - i]))
        tr.write(encode(Command.CAN_SEND_FRAME, payload))
        time.sleep(0.05)

    time.sleep(0.3)
    # Collect all loopback frames
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        frames = tr.incoming()
        for f in frames:
            if f.command == Command.CAN_FRAME_UP:
                received += 1
        time.sleep(0.02)

    if received >= 5:
        ok()
        print(f"         Received {received}/5 frames")
    else:
        fail(f"Only {received}/5 frames received")

    # ── Test 16: Stop CAN Listening ──────────────────────────────
    test("Stop CAN listening")
    tr.write(encode(Command.CAN_STOP_LISTEN))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
    else:
        ok()

    # ── Test 17: NACK on invalid command ─────────────────────────
    test("Invalid command returns NACK")
    tr.write(encode(Command.INVALID))
    nack_f = expect_frame(tr, Command.NACK, timeout=1.0)
    if nack_f is None:
        fail("No NACK")
    else:
        ok()

    # ── Cleanup ──────────────────────────────────────────────────
    tr.write(encode(Command.CAN_STOP_LISTEN))
    time.sleep(0.1)
    tr.disconnect()

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    if failed == 0:
        print("  VERDICT: ALL TESTS PASSED")
    else:
        print(f"  VERDICT: {failed} TEST(S) FAILED")
    print("=" * 60)


# ── Loopback-Only Quick Test ──────────────────────────────────────────


def run_loopback_test(port: str, baudrate: int = 115200):
    """Quick loopback test — no external CAN bus needed."""
    print("=" * 60)
    print(f"  Open-Canoe Loopback Self-Test")
    print(f"  Port: {port}  Baudrate: {baudrate}")
    print("=" * 60)

    tr = SerialTransport(port=port, baudrate=baudrate)

    try:
        tr.connect()
        print("  [OK] Connected")
    except Exception as e:
        print(f"  [FAIL] Connect: {e}")
        return

    hb = expect_frame(tr, Command.DEVICE_HEARTBEAT, timeout=3.0)
    if hb is None:
        print("  [FAIL] No heartbeat — is firmware flashed?")
        tr.disconnect()
        return
    info = unpack_heartbeat(hb.payload)
    print(f"  [OK] Device: {info['mcu_model']} FW v{info['fw_version']}")

    # Configure
    tr.write(encode(Command.CAN_SET_BAUDRATE, pack_can_set_baudrate(500000, 0)))
    expect_ack(tr)
    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(CAN_MODE_LOOPBACK, 0)))
    expect_ack(tr)
    tr.write(encode(Command.CAN_START_LISTEN))
    expect_ack(tr)
    print("  [OK] CAN configured: 500k, loopback mode")

    # Send test frames
    print("\n  Sending test frames in loopback...")
    for i in range(10):
        payload = pack_can_send_frame(
            can_id=0x100 + i, dlc=8,
            data=bytes([i, i+1, i+2, i+3, i+4, i+5, i+6, i+7])
        )
        tr.write(encode(Command.CAN_SEND_FRAME, payload))
        time.sleep(0.02)

    time.sleep(0.3)
    rx_count = 0
    while True:
        frames = tr.incoming()
        if not frames:
            break
        for f in frames:
            if f.command == Command.CAN_FRAME_UP:
                d = unpack_can_frame_up(f.payload)
                print(f"    RX: ID=0x{d['arbitration_id']:03X}  "
                      f"DLC={d['dlc']}  data={' '.join(f'{b:02X}' for b in d['data'])}")
                rx_count += 1

    print(f"\n  Sent: 10  Received: {rx_count}")
    if rx_count == 10:
        print("  [PASS] Loopback test successful!")
    else:
        print(f"  [WARN] Expected 10, got {rx_count}")

    tr.write(encode(Command.CAN_STOP_LISTEN))
    time.sleep(0.1)
    tr.disconnect()
    print("  [OK] Disconnected")


# ── Main ──────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Open-Canoe Hardware Test Suite"
    )
    parser.add_argument(
        "port", nargs="?", default=None,
        help="Serial port (e.g., COM7, /dev/ttyUSB0). Use --scan to find devices."
    )
    parser.add_argument(
        "--baud", type=int, default=115200,
        help="Baudrate (default: 115200)"
    )
    parser.add_argument(
        "--scan", action="store_true",
        help="Scan all ports for CAN probes"
    )
    parser.add_argument(
        "--loopback", action="store_true",
        help="Run quick loopback test only (no external CAN bus needed)"
    )
    parser.add_argument(
        "--full", action="store_true",
        help="Run full test suite"
    )

    args = parser.parse_args()

    if args.scan:
        cmd_scan()
        return

    if args.port is None:
        parser.print_help()
        print("\n  Provide a port, or use --scan to find devices.")
        sys.exit(1)

    if args.loopback:
        run_loopback_test(args.port, args.baud)
    else:
        run_tests(args.port, args.baud)


if __name__ == "__main__":
    main()
