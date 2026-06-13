#!/usr/bin/env python3
"""Open-Canoe Clean — remove build artifacts and caches."""

import os, shutil, sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

removed = []

# Recursively find and delete __pycache__
for root, dirs, files in os.walk(PROJECT_DIR):
    if "__pycache__" in dirs:
        p = os.path.join(root, "__pycache__")
        shutil.rmtree(p, ignore_errors=True)
        removed.append(p)
    if ".venv" in dirs:
        p = os.path.join(root, ".venv")
        shutil.rmtree(p, ignore_errors=True)
        removed.append(p)
    # Don't recurse into .git or node_modules
    dirs[:] = [d for d in dirs if d not in (".git", "node_modules")]

# Firmware build directories
fw_dir = os.path.join(PROJECT_DIR, "firmware")
if os.path.isdir(fw_dir):
    for d in os.listdir(fw_dir):
        if d.startswith("build_"):
            p = os.path.join(fw_dir, d)
            shutil.rmtree(p, ignore_errors=True)
            removed.append(p)

# uv lock file
lock_file = os.path.join(PROJECT_DIR, "open-canoe", "uv.lock")
if os.path.isfile(lock_file):
    os.remove(lock_file)
    removed.append(lock_file)

# History CSV files
data_dir = os.path.join(PROJECT_DIR, "open-canoe", "data")
if os.path.isdir(data_dir):
    for f in os.listdir(data_dir):
        if f.endswith(".csv"):
            p = os.path.join(data_dir, f)
            os.remove(p)
            removed.append(p)

for r in removed:
    print(f"  Removed: {r}")
print(f"\nDone — {len(removed)} items removed.")
