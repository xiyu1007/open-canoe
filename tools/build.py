#!/usr/bin/env python3
"""
Open-Canoe Unified Build & Flash Tool

Usage:
  python build.py list                  List supported MCU targets
  python build.py build <target>        Build firmware (target: f103, f407)
  python build.py flash <target>        Build + flash via ST-Link
  python build.py clean <target>        Clean build artifacts
  python build.py info                  Show ST-Link connected MCU

Examples:
  python build.py build f103
  python build.py flash f407
  python build.py list

App Integration:
  The App can call this script with the target selected from a dropdown.
  Build outputs go to build_f103/ or build_f407/.
"""

import sys
import os
import subprocess
import json
import glob

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HW_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "hardware")
ST_FLASH = os.path.join(
    os.path.dirname(SCRIPT_DIR), "assert",
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
        "hex": "open_canoe_f103.hex",
    },
    "f407": {
        "name": "STM32F407VET6",
        "makefile": "Makefile_f407",
        "build_dir": "build_f407",
        "flash_addr": "0x08000000",
        "bin": "open_canoe_f407.bin",
        "hex": "open_canoe_f407.hex",
    },
}


def find_make():
    """Find make executable on Windows."""
    candidates = [
        r"d:\Software\msys64\usr\bin\make.exe",
        r"d:\Software\msys64\mingw64\bin\mingw32-make.exe",
        "make",
        "mingw32-make",
    ]
    for c in candidates:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=5)
            return c
        except Exception:
            continue
    return None


def cmd_list():
    """List supported targets as JSON for the App."""
    targets = []
    for key, info in TARGETS.items():
        targets.append({
            "id": key,
            "name": info["name"],
            "build_dir": info["build_dir"],
        })
    print(json.dumps({"status": "ok", "targets": targets}, indent=2))


def cmd_build(target):
    """Build firmware for the given target."""
    if target not in TARGETS:
        print(json.dumps({"status": "error", "message": f"Unknown target: {target}"}))
        sys.exit(1)

    t = TARGETS[target]
    make = find_make()
    if not make:
        print(json.dumps({"status": "error", "message": "make not found"}))
        sys.exit(1)

    result = subprocess.run(
        [make, "-f", t["makefile"], "-j8"],
        cwd=HW_DIR,
        capture_output=True, text=True
    )

    if result.returncode != 0:
        print(json.dumps({
            "status": "error",
            "message": "Build failed",
            "output": result.stderr[-500:]
        }))
        sys.exit(1)

    bin_path = os.path.join(HW_DIR, t["build_dir"], t["bin"])
    hex_path = os.path.join(HW_DIR, t["build_dir"], t["hex"])
    size = os.path.getsize(bin_path) if os.path.exists(bin_path) else 0

    print(json.dumps({
        "status": "ok",
        "target": target,
        "bin": bin_path,
        "hex": hex_path,
        "size": size,
    }, indent=2))


def cmd_flash(target):
    """Build and flash via ST-Link."""
    cmd_build(target)  # Build first (exits on failure)

    t = TARGETS[target]
    bin_path = os.path.join(HW_DIR, t["build_dir"], t["bin"])

    if not os.path.exists(ST_FLASH):
        print(json.dumps({"status": "error", "message": f"st-flash not found: {ST_FLASH}"}))
        sys.exit(1)

    result = subprocess.run(
        [ST_FLASH, "--reset", "write", bin_path, t["flash_addr"]],
        capture_output=True, text=True
    )

    if "jolly good" in (result.stdout + result.stderr):
        print(json.dumps({"status": "ok", "message": "Flash successful"}))
    else:
        print(json.dumps({
            "status": "error",
            "message": "Flash failed",
            "output": result.stdout[-200:] + result.stderr[-200:]
        }))
        sys.exit(1)


def cmd_clean(target):
    """Clean build artifacts."""
    if target not in TARGETS:
        print(json.dumps({"status": "error", "message": f"Unknown target: {target}"}))
        sys.exit(1)

    t = TARGETS[target]
    make = find_make()
    if not make:
        print(json.dumps({"status": "error", "message": "make not found"}))
        sys.exit(1)

    subprocess.run(
        [make, "-f", t["makefile"], "clean"],
        cwd=HW_DIR,
        capture_output=True
    )
    print(json.dumps({"status": "ok", "message": f"Cleaned {target}"}))


def cmd_info():
    """Probe ST-Link for connected MCU info."""
    st_info = ST_FLASH.replace("st-flash.exe", "st-info.exe")
    if not os.path.exists(st_info):
        print(json.dumps({"status": "error", "message": "st-info not found"}))
        sys.exit(1)

    result = subprocess.run([st_info, "--probe"], capture_output=True, text=True)
    print(json.dumps({
        "status": "ok",
        "output": result.stdout.strip()
    }, indent=2))


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "list":
        cmd_list()
    elif cmd == "build":
        cmd_build(target)
    elif cmd == "flash":
        cmd_flash(target)
    elif cmd == "clean":
        cmd_clean(target)
    elif cmd == "info":
        cmd_info()
    else:
        print(json.dumps({"status": "error", "message": f"Unknown command: {cmd}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
