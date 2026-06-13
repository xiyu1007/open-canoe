#!/usr/bin/env python3
"""Open-Canoe Deploy — Build firmware, flash via ST-Link, launch App."""

import sys, os, subprocess, json, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
HW_DIR = os.path.join(PROJECT_DIR, "firmware")
APP_DIR = os.path.join(PROJECT_DIR, "open-canoe")

ST_FLASH = os.environ.get("ST_FLASH", os.path.join(
    PROJECT_DIR, "assert", "stlink-1.7.0-x86_64-w64-mingw32",
    "stlink-1.7.0-x86_64-w64-mingw32", "bin", "st-flash.exe"))

TARGET = {
    "name": "STM32F103C8T6",
    "makefile": "Makefile_f103",
    "build_dir": "build_f103",
    "flash_addr": "0x08000000",
    "bin": "open_canoe_f103.bin",
}


def find_make():
    for c in [r"d:\Software\msys64\usr\bin\make.exe",
              r"d:\Software\msys64\mingw64\bin\mingw32-make.exe",
              "make", "mingw32-make"]:
        try:
            subprocess.run([c, "--version"], capture_output=True, timeout=5)
            return c
        except Exception:
            continue
    return None


def build():
    make = find_make()
    if not make:
        print("ERROR: make not found")
        sys.exit(1)
    # Ensure build dir exists (make's mkdir fails on some Windows shells)
    build_dir = os.path.join(HW_DIR, TARGET["build_dir"])
    os.makedirs(build_dir, exist_ok=True)
    # Add msys2 bin to PATH so make can find mkdir/sh/etc.
    env = os.environ.copy()
    make_dir = os.path.dirname(os.path.abspath(make))
    msys_bin = os.path.join(os.path.dirname(make_dir), "usr", "bin")
    if os.path.isdir(msys_bin):
        env["PATH"] = make_dir + os.pathsep + msys_bin + os.pathsep + env.get("PATH", "")
    elif make_dir not in env.get("PATH", ""):
        env["PATH"] = make_dir + os.pathsep + env.get("PATH", "")
    print(f"Building {TARGET['name']} ...")
    result = subprocess.run([make, "-f", TARGET["makefile"], "-j8"],
                            cwd=HW_DIR, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"BUILD FAILED:\n{result.stderr[-500:]}")
        sys.exit(1)
    print("Build OK")


def flash():
    bin_path = os.path.join(HW_DIR, TARGET["build_dir"], TARGET["bin"])
    if not os.path.exists(bin_path):
        print(f"ERROR: binary not found: {bin_path}")
        sys.exit(1)
    if not os.path.exists(ST_FLASH):
        print(f"ERROR: st-flash not found: {ST_FLASH}")
        sys.exit(1)
    print("Flashing ...")
    result = subprocess.run([ST_FLASH, "--reset", "write", bin_path, TARGET["flash_addr"]],
                            capture_output=True, text=True)
    if "jolly good" not in (result.stdout + result.stderr):
        print(f"FLASH FAILED:\n{result.stdout[-300:]}\n{result.stderr[-300:]}")
        sys.exit(1)
    print("Flash OK")


def launch():
    print("Launching App ...")
    env = os.environ.copy()
    env.pop("VIRTUAL_ENV", None)
    subprocess.Popen(["uv", "run", "--no-progress", "python", "main.py"],
                     cwd=APP_DIR, env=env, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    print(f"Open-Canoe Deploy — {TARGET['name']}")
    build()
    flash()
    time.sleep(0.5)
    launch()
