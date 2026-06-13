#!/usr/bin/env python3
"""
Open-Canoe One-Click Deploy & Test Script

Performs the full workflow:
  1. Build firmware
  2. Flash via ST-Link
  3. Run hardware protocol tests
  4. (optional) Launch the desktop app

Usage:
  python scripts/deploy.py f103              # Build, flash, test F103
  python scripts/deploy.py f103 --run-app    # Build, flash, test, launch app
  python scripts/deploy.py f103 --test-only  # Run tests only (no build/flash)
  python scripts/deploy.py f103 --port COM7  # Use specific port for tests

Output: JSON status for each step.
"""

import sys
import os
import subprocess
import json
import time
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
TOOLS_DIR = os.path.join(PROJECT_DIR, "tools")
FW_DIR = os.path.join(PROJECT_DIR, "firmware")
APP_DIR = os.path.join(PROJECT_DIR, "open-canoe")
TEST_DIR = os.path.join(PROJECT_DIR, "test")
ST_FLASH = os.path.join(
    PROJECT_DIR, "assert",
    "stlink-1.7.0-x86_64-w64-mingw32",
    "stlink-1.7.0-x86_64-w64-mingw32", "bin", "st-flash.exe"
)

TARGETS = {
    "f103": {
        "name": "STM32F103C8T6",
        "makefile": "Makefile_f103",
        "build_dir": "build_f103",
        "flash_addr": "0x08000000",
        "bin": "open_canoe_f103.bin",
    },
    "f407": {
        "name": "STM32F407VET6",
        "makefile": "Makefile_f407",
        "build_dir": "build_f407",
        "flash_addr": "0x08000000",
        "bin": "open_canoe_f407.bin",
    },
}

MAKE_PATH = "d:/Software/msys64/usr/bin/make.exe"
GCC_PATH = "d:/STM32/Environment/gcc-arm-none-eabi-10.3-2021.10/bin"


def find_com_port():
    """Auto-detect a CAN probe COM port."""
    sys.path.insert(0, APP_DIR)
    from core.transport import list_serial_ports, _try_heartbeat
    ports = list_serial_ports()
    for p in ports:
        for br in [115200, 921600]:
            hb = _try_heartbeat(p.port, br, timeout=0.8)
            if hb:
                return p.port, br
    return None, None


def step(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def build_firmware(target):
    """Build firmware. Returns (success, message)."""
    t = TARGETS[target]
    step(f"Building {t['name']}")

    env = os.environ.copy()
    env["PATH"] = f"{MAKE_PATH.rsplit('/', 2)[0]};{GCC_PATH};{env['PATH']}"

    result = subprocess.run(
        [MAKE_PATH, "-f", t["makefile"], "-j8"],
        cwd=FW_DIR, env=env,
        capture_output=True, text=True
    )

    if result.returncode != 0:
        print(f"  [FAIL] Build failed:\n{result.stderr[-500:]}")
        return False, result.stderr[-200:]
    print(f"  [OK] Build succeeded")
    return True, "ok"


def flash_firmware(target):
    """Flash firmware via ST-Link. Returns (success, message)."""
    t = TARGETS[target]
    step(f"Flashing {t['name']}")

    bin_path = os.path.join(FW_DIR, t["build_dir"], t["bin"])
    if not os.path.exists(bin_path):
        print(f"  [FAIL] Binary not found: {bin_path}")
        return False, "binary not found"

    if not os.path.exists(ST_FLASH):
        print(f"  [FAIL] st-flash not found: {ST_FLASH}")
        return False, "st-flash not found"

    result = subprocess.run(
        [ST_FLASH, "--reset", "write", bin_path, t["flash_addr"]],
        capture_output=True, text=True
    )

    if "jolly good" in (result.stdout + result.stderr):
        print(f"  [OK] Flash successful")
        return True, "ok"
    else:
        print(f"  [FAIL] Flash failed:\n{result.stdout[-300:]}\n{result.stderr[-300:]}")
        return False, result.stdout[-200:] + result.stderr[-200:]


def run_tests(target, port=None, baudrate=115200):
    """Run hardware protocol tests. Returns (passed, total, output)."""
    step(f"Running hardware tests")

    if port is None:
        print("  Auto-detecting COM port...")
        port, detected_br = find_com_port()
        if port:
            baudrate = detected_br or baudrate
            print(f"  Found device on {port} @ {baudrate}")
        else:
            print("  [WARN] No device auto-detected, trying COM7")
            port = "COM7"

    sys.path.insert(0, APP_DIR)
    from test_hardware import run_tests as _run_tests

    # Redirect test output to capture
    import io
    old_stdout = sys.stdout
    sys.stdout = captured = io.StringIO()

    try:
        _run_tests(port, baudrate)
    except Exception as e:
        print(f"  [FAIL] Test error: {e}")

    sys.stdout = old_stdout
    output = captured.getvalue()
    print(output)

    # Parse results
    passed = output.count("PASS")
    failed = output.count("FAIL")
    return passed, passed + failed, output


def launch_app(port=None):
    """Launch the desktop GUI application."""
    step("Launching App")
    cmd = [sys.executable, "main.py"]
    print(f"  Starting: cd {APP_DIR} && python main.py")
    subprocess.Popen(cmd, cwd=APP_DIR)


def main():
    parser = argparse.ArgumentParser(
        description="Open-Canoe One-Click Deploy & Test"
    )
    parser.add_argument("target", nargs="?", default="f103",
                        choices=["f103", "f407"],
                        help="MCU target (default: f103)")
    parser.add_argument("--run-app", action="store_true",
                        help="Launch desktop app after deploy")
    parser.add_argument("--test-only", action="store_true",
                        help="Only run tests (skip build and flash)")
    parser.add_argument("--port", default=None,
                        help="COM port for tests (auto-detect if not specified)")
    parser.add_argument("--build-only", action="store_true",
                        help="Only build (skip flash and tests)")
    parser.add_argument("--flash-only", action="store_true",
                        help="Only flash (skip build and tests)")

    args = parser.parse_args()

    print("=" * 60)
    print(f"  Open-Canoe Deploy — {TARGETS[args.target]['name']}")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = {"steps": {}}

    if args.test_only:
        p, t, out = run_tests(args.target, args.port)
        results["steps"]["test"] = {"passed": p, "total": t}
    elif args.build_only:
        ok, msg = build_firmware(args.target)
        results["steps"]["build"] = {"ok": ok, "message": msg}
    elif args.flash_only:
        ok, msg = flash_firmware(args.target)
        results["steps"]["flash"] = {"ok": ok, "message": msg}
    else:
        # Full deploy: build → flash → test
        ok, msg = build_firmware(args.target)
        results["steps"]["build"] = {"ok": ok, "message": msg}
        if not ok:
            print("\n  Build failed — stopping.")
            sys.exit(1)

        ok, msg = flash_firmware(args.target)
        results["steps"]["flash"] = {"ok": ok, "message": msg}
        if not ok:
            print("\n  Flash failed — stopping.")
            sys.exit(1)

        time.sleep(0.5)  # Let MCU boot
        p, t, out = run_tests(args.target, args.port)
        results["steps"]["test"] = {"passed": p, "total": t}

    if args.run_app:
        launch_app(args.port)

    # Summary
    print(f"\n{'='*60}")
    print(f"  DEPLOY COMPLETE")
    print(f"  Results: {json.dumps(results['steps'], indent=2)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
