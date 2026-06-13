"""Full GUI integration test — simulates clicks via invoke(), verifies logs and message table.

Per REQUIREMENTS.md §10: 9-step test criteria.
"""
import os, sys, time

# HOME dir for tkinter — use env var if set, otherwise user home
if 'HOME' not in os.environ:
    os.environ['HOME'] = os.path.expanduser('~')

# Add open-canoe/ to path (project root = parent of test/)
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_PROJ_ROOT, 'open-canoe'))

from gui.app import MainWindow  # noqa: E402

app = MainWindow()
L_ = app  # keep reference alive

results = []

def log(msg):
    print(f"  {msg}")

def check(step, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {step}{' — ' + detail if detail else ''}")
    results.append((step, status == "PASS", detail))
    return condition

# ── Helper: pump tkinter events ──────────────────────────────
def pump(seconds=0.5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.02)

# ── Helper: get message table rows ───────────────────────────
def get_rows():
    rows = []
    for child in app._tbl._tree.get_children():
        vals = app._tbl._tree.item(child, 'values')
        # vals = [序号, 时间, CAN_ID, 类型, DLC, 方向, 数据, 通道]
        rows.append(vals)
    return rows

# ── Helper: get log text ─────────────────────────────────────
def get_log():
    return app._log._text.get('1.0', 'end-1c')

# ── Helper: count TX/RX in message table ────────────────────
def count_direction(direction='TX'):
    return sum(1 for r in get_rows() if len(r) > 5 and r[5] == direction)

# ═══════════════════════════════════════════════════════════════
# STEP 1: Select port and connect
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 1: Connect ===")
app._dev._port_var.set('COM7')

# Click connect button
app._dev._btn.invoke()
log("Connect button clicked, waiting for device...")

# Wait for connection (up to 15s)
connected = False
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    app.root.update()
    time.sleep(0.03)
    if app._tr and app._tr.is_connected:
        connected = True
        break

check("1.1 Device connected", connected, f"is_connected={app._tr is not None and app._tr.is_connected if app._tr else False}")

# Wait for CAN config (300ms after connect)
pump(2.0)

log_text = get_log()
check("1.2 Device info in log", "Device:" in log_text and "FW:" in log_text, "Device info shown")
check("1.3 Capabilities in log", "Capabilities:" in log_text, "Capabilities displayed")
check("1.4 CAN configured in log", "CAN configured:" in log_text, "CAN config displayed")

# ═══════════════════════════════════════════════════════════════
# STEP 2: Send in NORMAL mode (no loopback)
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 2: Send NORMAL mode ===")

# Clear table first
app._tbl.clear()
pump(0.2)

# Fill in send data
app._snd._id_var.set('0x123')
app._snd._data_var.set('AA BB CC DD')
app._snd._dlc_var.set('4')

# Click single send button
app._snd._btn_once.invoke()
pump(1.0)

rows = get_rows()
tx_count = count_direction('TX')
rx_count = count_direction('RX')

check("2.1 TX row appears", tx_count >= 1, f"TX count={tx_count}")
check("2.2 NO RX row (NORMAL mode)", rx_count == 0, f"RX count={rx_count}")

log_text = get_log()
check("2.3 No TX error in log", "CMD 0x34 failed" not in log_text, "No CMD 0x34 failed")
check("2.4 No CAN TX failed in log", "CAN TX failed" not in log_text, "No CAN TX failed")

# ═══════════════════════════════════════════════════════════════
# STEP 3: Send NORMAL x5
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 3: Send NORMAL x5 ===")
app._tbl.clear()
pump(0.2)

for i in range(5):
    app._snd._id_var.set(f'0x{0x200 + i:03X}')
    app._snd._btn_once.invoke()
    pump(0.3)

tx_count = count_direction('TX')
rx_count = count_direction('RX')
check("3.1 All 5 TX appear", tx_count == 5, f"TX count={tx_count}")
check("3.2 Still NO RX", rx_count == 0, f"RX count={rx_count}")

log_text = get_log()
check("3.3 No errors in log after 5 sends", "CMD 0x34 failed" not in log_text)

# ═══════════════════════════════════════════════════════════════
# STEP 4: Switch to LOOPBACK mode
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 4: Enable LOOPBACK ===")

app._dev._loopback_var.set(True)
app._on_loopback(True)
pump(1.0)

log_text = get_log()
check("4.1 Loopback mode logged", "loopback" in log_text.lower(), "Mode switch to loopback")

# ═══════════════════════════════════════════════════════════════
# STEP 5: Send in LOOPBACK mode
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 5: Send LOOPBACK mode ===")
app._tbl.clear()
pump(0.2)

app._snd._id_var.set('0x123')
app._snd._data_var.set('AA BB CC DD')
app._snd._dlc_var.set('4')
app._snd._btn_once.invoke()
pump(1.5)

tx_count = count_direction('TX')
rx_count = count_direction('RX')
rows = get_rows()

check("5.1 TX row appears", tx_count >= 1, f"TX count={tx_count}")
check("5.2 RX row appears", rx_count >= 1, f"RX count={rx_count}")

# Verify RX data matches TX
rx_row = None
for r in rows:
    if len(r) > 5 and r[5] == 'RX':
        rx_row = r
        break

if rx_row:
    # vals = [序号, 时间, CAN_ID, 类型, DLC, 方向, 数据, 通道]
    check("5.3 RX ID matches TX", rx_row[2] == '0x123', f"RX ID={rx_row[2]}")
    check("5.4 RX DLC matches", rx_row[4] == '4', f"RX DLC={rx_row[4]}")
    check("5.5 RX data matches", rx_row[6] == 'AA BB CC DD', f"RX data={rx_row[6]}")

log_text = get_log()
check("5.6 No TX error in log", "CMD 0x34 failed" not in log_text)

# ═══════════════════════════════════════════════════════════════
# STEP 6: Cycle send x10 in LOOPBACK
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 6: Cycle x10 LOOPBACK ===")
app._tbl.clear()
pump(0.2)

app._snd._id_var.set('0x300')
app._snd._data_var.set('11 22 33 44 55 66 77 88')
app._snd._dlc_var.set('8')

for i in range(10):
    app._snd._btn_once.invoke()
    pump(0.5)  # Allow time for loopback RX poll + CAN_FRAME_UP + ACK

tx_count = count_direction('TX')
rx_count = count_direction('RX')
check("6.1 All 10 TX appear", tx_count == 10, f"TX count={tx_count}")
check("6.2 All 10 RX appear", rx_count == 10, f"RX count={rx_count}")

log_text = get_log()
check("6.3 No errors after cycle x10", "CMD 0x34 failed" not in log_text)

# ═══════════════════════════════════════════════════════════════
# STEP 7: Switch back to NORMAL
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 7: Disable LOOPBACK → NORMAL ===")

app._dev._loopback_var.set(False)
app._on_loopback(False)
pump(1.0)

log_text = get_log()
check("7.1 Normal mode logged", "normal" in log_text.lower(), "Mode switch to normal")

# ═══════════════════════════════════════════════════════════════
# STEP 8: Send NORMAL again (verify no stale ghost RX)
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 8: Send NORMAL after loopback ===")
app._tbl.clear()
pump(0.2)

app._snd._id_var.set('0x456')
app._snd._data_var.set('DE AD BE EF')
app._snd._dlc_var.set('4')
app._snd._btn_once.invoke()
pump(1.0)

tx_count = count_direction('TX')
rx_count = count_direction('RX')

check("8.1 TX row appears", tx_count >= 1, f"TX count={tx_count}")
check("8.2 NO RX row (NORMAL, no ghost)", rx_count == 0, f"RX count={rx_count}")

log_text = get_log()
check("8.3 No TX error", "CMD 0x34 failed" not in log_text)

# ═══════════════════════════════════════════════════════════════
# STEP 9: Disconnect
# ═══════════════════════════════════════════════════════════════
print("\n=== STEP 9: Disconnect ===")
app._disconnect()
pump(0.5)

check("9.1 Transport disconnected", app._tr is None, f"tr={app._tr}")
status = app._status_var.get()
check("9.2 Status shows disconnected", "未连接" in status or "disconnected" in status.lower(), f"status={status}")

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
print(f"RESULTS: {passed}/{total} PASSED")
print("=" * 60)

for step, ok, detail in results:
    if not ok:
        print(f"  FAIL: {step} — {detail}")

app.root.destroy()

# Exit code
if passed == total:
    print("\nALL TESTS PASSED!")
    sys.exit(0)
else:
    print(f"\n{total - passed} TESTS FAILED!")
    sys.exit(1)
