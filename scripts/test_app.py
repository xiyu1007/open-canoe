#!/usr/bin/env python3
"""
Open-Canoe App Simulation Test

Simulates operating the desktop app by sending protocol commands directly
to the CAN probe. This tests the complete App→FW→App communication cycle
without needing to run the tkinter GUI.

Usage:
  python scripts/test_app.py COM7              # Run all app simulation tests
  python scripts/test_app.py COM7 --loopback   # Loopback mode tests only
  python scripts/test_app.py --scan            # Auto-detect and test
  python scripts/test_app.py COM7 --cycle 100  # Cycle send 100 frames at 100ms

Simulates these app operations:
  1. Device discovery / heartbeat
  2. Capability query
  3. CAN configuration (baudrate, mode)
  4. Send CAN frames (standard, extended, remote)
  5. Cycle send with configurable count/interval
  6. Mode switching (normal ↔ listen-only ↔ loopback)
  7. Status polling
  8. Error handling
"""

import sys
import os
import time
import argparse
import threading

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
APP_DIR = os.path.join(PROJECT_DIR, "open-canoe")
sys.path.insert(0, APP_DIR)

from core.transport import (
    SerialTransport, TransportError, list_serial_ports, _try_heartbeat,
)
from core.protocol import (
    Command, Frame, encode, decode,
    pack_can_send_frame, pack_can_set_baudrate, pack_can_set_mode,
    unpack_can_frame_up, unpack_device_info, unpack_capabilities,
    unpack_heartbeat, unpack_status, unpack_ack, unpack_error_notify,
    CAN_MODE_NORMAL, CAN_MODE_LISTEN_ONLY, CAN_MODE_LOOPBACK,
    CAN_MODE_LOOPBACK_SILENT,
    ERR_NONE, ERROR_MESSAGES, FRAME_OVERHEAD, MAGIC_HEADER,
)

PASS = 0
FAIL = 0
TOTAL = 0
_stash: list = []  # Stash for non-matching frames between expect calls


def test(name):
    global TOTAL
    TOTAL += 1
    print(f"\n  [{TOTAL}] {name}...", end=" ")
    return name


def ok(msg=""):
    global PASS
    PASS += 1
    extra = f" — {msg}" if msg else ""
    print(f"PASS{extra}")


def fail(msg=""):
    global FAIL
    FAIL += 1
    extra = f" — {msg}" if msg else ""
    print(f"FAIL{extra}")


def expect(tr, cmd, timeout=2.0):
    """Wait for a specific frame type. Stashes non-matching frames."""
    global _stash
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for i, f in enumerate(_stash):
            if f.command == cmd:
                return _stash.pop(i)
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


def expect_ack(tr, timeout=1.0):
    f = expect(tr, Command.ACK, timeout)
    return unpack_ack(f.payload) if f else None


def scan_and_select():
    """Scan ports and let user select or auto-detect CAN probe."""
    ports = list_serial_ports()
    if not ports:
        print("No serial ports found.")
        return None, None

    print("Available ports:")
    for i, p in enumerate(ports):
        print(f"  [{i}] {p.port:10s} {p.description}")

    # Try auto-detect
    for p in ports:
        for br in [115200, 921600]:
            hb = _try_heartbeat(p.port, br, timeout=0.8)
            if hb:
                print(f"\n  Auto-detected: {p.port} @ {br} — {hb['mcu_model']}")
                return p.port, br

    # Fallback: use first port
    print(f"\n  No device auto-detected. Using {ports[0].port}")
    return ports[0].port, 115200


# ── App Simulation Tests ────────────────────────────────────────────


def test_connect(tr):
    """Simulate app connection: heartbeat detection."""
    test("App connect (heartbeat)")
    hb_f = expect(tr, Command.DEVICE_HEARTBEAT, timeout=3.0)
    if hb_f is None:
        # Already sent, use GET_INFO as fallback
        tr.write(encode(Command.GET_INFO))
        info_f = expect(tr, Command.INFO_RESPONSE, timeout=2.0)
        if info_f:
            info = unpack_device_info(info_f.payload)
            ok(f"FW v{info['fw_version']}")
            return info
        fail("no heartbeat and no INFO response")
        return None
    hb = unpack_heartbeat(hb_f.payload)
    ok(f"{hb['mcu_model']} v{hb['fw_version']}")
    return hb


def test_capabilities(tr):
    """Simulate app capability query."""
    test("Query capabilities")
    tr.write(encode(Command.GET_CAPABILITIES))
    caps_f = expect(tr, Command.CAPABILITIES_RESP, timeout=2.0)
    if caps_f is None:
        fail("no response")
        return None
    caps = unpack_capabilities(caps_f.payload)
    ok(f"ADC={caps['has_adc']} USB_CDC={caps['has_usb_cdc']} CAN={caps['can_channel_count']}ch")
    return caps


def test_status(tr):
    """Simulate app status poll."""
    test("Query status")
    tr.write(encode(Command.GET_STATUS))
    st_f = expect(tr, Command.STATUS_RESPONSE, timeout=2.0)
    if st_f is None:
        fail("no response")
        return None
    st = unpack_status(st_f.payload)
    ok(f"uptime={st['uptime_ms']}ms can={st['can_listening']}")
    return st


def test_config_can(tr, baudrate=500000, mode=CAN_MODE_NORMAL):
    """Simulate app CAN configuration."""
    test(f"Configure CAN: {baudrate//1000}kbps mode={mode}")
    tr.write(encode(Command.CAN_SET_BAUDRATE, pack_can_set_baudrate(baudrate, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"baudrate: {ack}")
        return False

    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(mode, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"mode: {ack}")
        return False

    tr.write(encode(Command.CAN_START_LISTEN))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"listen: {ack}")
        return False

    ok()
    return True


def test_send_frame(tr, can_id, data, is_extended=False, is_remote=False,
                    expect_loopback=True, label=""):
    """Simulate app sending a single CAN frame. Checks for software loopback."""
    global _stash
    desc = label or f"0x{can_id:X}"
    test(f"Send CAN frame: {desc}")
    _stash.clear()
    payload = pack_can_send_frame(can_id, len(data), is_extended, is_remote, 0, data)
    tr.write(encode(Command.CAN_SEND_FRAME, payload))

    if expect_loopback:
        rx_f = expect(tr, Command.CAN_FRAME_UP, timeout=2.0)
        if rx_f is None:
            fail("no loopback RX")
            return None
        d = unpack_can_frame_up(rx_f.payload)
        ok(f"RX 0x{d['arbitration_id']:X} DLC={d['dlc']}")
        return d
    else:
        # Just check ACK
        ack = expect_ack(tr)
        ok("TX OK" if ack and ack["error_code"] == 0 else f"ACK err={ack}")
        return None


def test_cycle_send(tr, count=10, interval_ms=100):
    """Simulate app cycle send with configurable count and interval."""
    test(f"Cycle send: {count} frames @ {interval_ms}ms")
    received = 0
    for i in range(count):
        can_id = 0x200 + i
        data = bytes([i, (i+1) & 0xFF, 0xAA, 0x55])
        payload = pack_can_send_frame(can_id, len(data))
        tr.write(encode(Command.CAN_SEND_FRAME, payload))
        time.sleep(interval_ms / 1000.0)

    # Collect results
    time.sleep(0.3)
    while True:
        frames = tr.incoming()
        if not frames:
            break
        for f in frames:
            if f.command == Command.CAN_FRAME_UP:
                received += 1

    if received >= count:
        ok(f"{received}/{count} received")
    else:
        fail(f"only {received}/{count} received")
    return received


def test_mode_switch(tr, mode, name):
    """Simulate app mode switch (silent, loopback, etc.)."""
    global _stash
    test(f"Switch to {name} mode")
    _stash.clear()
    tr.write(encode(Command.CAN_SET_MODE, pack_can_set_mode(mode, 0)))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"ACK error: {ack}")
        return False
    ok()
    return True


def test_device_info(tr):
    """Simulate app device info query."""
    test("Query device info")
    tr.write(encode(Command.GET_INFO))
    info_f = expect(tr, Command.INFO_RESPONSE, timeout=2.0)
    if info_f is None:
        fail("no response")
        return None
    info = unpack_device_info(info_f.payload)
    ok(f"SN={info['device_serial']} {info['mcu_model']}")
    return info


def test_disconnect(tr):
    """Simulate app disconnect sequence."""
    global _stash
    test("App disconnect (stop CAN + close)")
    _stash.clear()
    tr.write(encode(Command.CAN_STOP_LISTEN))
    ack = expect_ack(tr)
    if ack is None or ack["error_code"] != ERR_NONE:
        fail(f"stop listen: {ack}")
    else:
        ok()


# ── Main Test Runner ───────────────────────────────────────────────


def run_app_simulation(port, baudrate=115200, loopback_only=False,
                       cycle_count=10, cycle_interval_ms=100):
    global PASS, FAIL, TOTAL, _stash
    PASS = FAIL = TOTAL = 0
    _stash.clear()

    print("=" * 60)
    print(f"  Open-Canoe App Simulation Test")
    print(f"  Port: {port}  Baudrate: {baudrate}")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    tr = SerialTransport(port=port, baudrate=baudrate)

    try:
        tr.connect()
        print("\n  [OK] Serial port opened")
    except Exception as e:
        fail(f"Connect: {e}")
        return

    time.sleep(0.3)

    # ── Phase 1: Connection & Discovery ──────────────────────────
    hb = test_connect(tr)
    if hb is None:
        tr.disconnect()
        return

    caps = test_capabilities(tr)
    test_device_info(tr)
    test_status(tr)

    # ── Phase 2: CAN Configuration ────────────────────────────────
    if not test_config_can(tr, 500000, CAN_MODE_LOOPBACK if loopback_only else CAN_MODE_NORMAL):
        tr.disconnect()
        return

    # ── Phase 3: Frame Transmission ───────────────────────────────
    test_send_frame(tr, 0x123, bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11]),
                    label="standard 8-byte")

    test_send_frame(tr, 0x18DAF110, bytes([1, 2, 3, 4]),
                    is_extended=True, label="extended 29-bit")

    test_send_frame(tr, 0x456, bytes([0x10, 0x20, 0x30]),
                    is_remote=True, label="remote frame")

    test_send_frame(tr, 0x7DF, bytes([0x02, 0x01, 0x00]),
                    label="OBD-II request")

    # ── Phase 4: Cycle Send ───────────────────────────────────────
    test_cycle_send(tr, min(cycle_count, 5), cycle_interval_ms)

    if not loopback_only:
        # ── Phase 5: Mode Switching ───────────────────────────────
        test_mode_switch(tr, CAN_MODE_LISTEN_ONLY, "listen-only")
        test_mode_switch(tr, CAN_MODE_NORMAL, "normal")

        # ── Phase 6: Loopback Test ────────────────────────────────
        test_mode_switch(tr, CAN_MODE_LOOPBACK, "loopback")
        test_send_frame(tr, 0x300, bytes([0xDE, 0xAD, 0xBE, 0xEF]),
                        label="loopback test")
        test_mode_switch(tr, CAN_MODE_NORMAL, "normal")

    # ── Phase 7: Cycle Send (larger) ──────────────────────────────
    if not loopback_only and cycle_count > 5:
        test_cycle_send(tr, cycle_count, cycle_interval_ms)

    # ── Phase 8: Final Status ─────────────────────────────────────
    test_status(tr)

    # ── Phase 9: Disconnect ───────────────────────────────────────
    test_disconnect(tr)

    tr.disconnect()

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"  APP SIMULATION RESULTS: {PASS}/{TOTAL} passed, {FAIL}/{TOTAL} failed")
    if FAIL == 0:
        print("  VERDICT: ALL TESTS PASSED")
    else:
        print(f"  VERDICT: {FAIL} TEST(S) FAILED")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Open-Canoe App Simulation Test"
    )
    parser.add_argument("port", nargs="?", default=None,
                        help="Serial port (auto-detect if not specified)")
    parser.add_argument("--baud", type=int, default=115200,
                        help="Baudrate (default: 115200)")
    parser.add_argument("--scan", action="store_true",
                        help="Scan for devices then test")
    parser.add_argument("--loopback", action="store_true",
                        help="Loopback mode only (faster)")
    parser.add_argument("--cycle", type=int, default=10,
                        help="Cycle send count (default: 10)")
    parser.add_argument("--interval", type=int, default=100,
                        help="Cycle send interval in ms (default: 100)")

    args = parser.parse_args()

    if args.scan or args.port is None:
        port, br = scan_and_select()
        if port is None:
            print("\n  No device found. Connect a CAN probe and retry.")
            sys.exit(1)
        if args.port is None:
            args.port = port
        args.baud = br

    run_app_simulation(
        port=args.port,
        baudrate=args.baud,
        loopback_only=args.loopback,
        cycle_count=args.cycle,
        cycle_interval_ms=args.interval,
    )


if __name__ == "__main__":
    main()
