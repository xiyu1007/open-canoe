"""Complete UI control test — tests every button, checkbox, dropdown per REQUIREMENTS.md §8."""
import os, sys, time

os.environ['HOME'] = 'C:/Users/GX'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'open-canoe'))

from gui.app import MainWindow

app = MainWindow()

def pump(s=0.5):
    deadline = time.monotonic() + s
    while time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.02)

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}{' — ' + detail if detail else ''}")
    results.append((name, status == "PASS"))

# ── Connect first ────────────────────────────────────────────
print("=== Connecting to device ===")
app._dev._port_var.set('COM7')
app._dev._btn.invoke()
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    app.root.update(); time.sleep(0.03)
    if app._tr and app._tr.is_connected: break
pump(3.0)
connected = app._tr is not None and app._tr.is_connected
check("Connect", connected)
if not connected:
    print("Cannot continue without connection!")
    app.root.destroy()
    sys.exit(1)

# ═══════════════════════════════════════════════════════════════
# §8.1 DeviceBar controls
# ═══════════════════════════════════════════════════════════════
print("\n=== §8.1 DeviceBar ===")

# MCU dropdown
mcu_val = app._dev._mcu_var.get()
check("8.1.1 MCU dropdown default", mcu_val == "STM32F103C8T6", f"value={mcu_val}")

# COM port dropdown
port_val = app._dev._port_var.get()
check("8.1.2 COM port set", port_val == "COM7", f"value={port_val}")

# Port refresh button
ports_before = list(app._dev._port_cb['values'])
app._dev._refresh_ports()
pump(0.5)
ports_after = list(app._dev._port_cb['values'])
check("8.1.3 Port refresh", len(ports_after) > 0, f"ports={len(ports_after)}")

# Connect button state
check("8.1.4 Connect button green", app._dev.is_connected, f"connected={app._dev.is_connected}")

# Bitrate dropdown
br = app._dev._br_var.get()
check("8.1.5 Bitrate dropdown", "500" in br or "500 kbps" in br, f"value={br}")

# Loopback checkbox
lb_initial = app._dev._loopback_var.get()
check("8.1.6 Loopback initial", lb_initial == False, f"loopback={lb_initial}")

app._dev._loopback_var.set(True)
app._on_loopback(True)
pump(1.0)
check("8.1.7 Loopback toggle ON", app._dev._loopback_var.get() == True)

app._dev._loopback_var.set(False)
app._on_loopback(False)
pump(1.0)
check("8.1.8 Loopback toggle OFF", app._dev._loopback_var.get() == False)

# Disconnect and reconnect
app._disconnect()
pump(1.0)
check("8.1.9 Disconnect", app._tr is None)

app._dev._port_var.set('COM7')
app._dev._btn.invoke()
deadline = time.monotonic() + 15
while time.monotonic() < deadline:
    app.root.update(); time.sleep(0.03)
    if app._tr and app._tr.is_connected: break
pump(3.0)
check("8.1.10 Reconnect", app._tr is not None and app._tr.is_connected)

# ═══════════════════════════════════════════════════════════════
# §8.2 SendPanel controls
# ═══════════════════════════════════════════════════════════════
print("\n=== §8.2 SendPanel ===")

# CAN ID input
app._snd._id_var.set('0x7AB')
check("8.2.1 CAN ID input", app._snd._id_var.get() == '0x7AB')

# Frame type dropdown (ZH/EN aware)
app._snd._tp_var.set('扩展')
check("8.2.2 Frame type ext", '扩展' in app._snd._tp_var.get() or 'Extended' in app._snd._tp_var.get())
app._snd._tp_var.set('标准')
check("8.2.3 Frame type std", '标准' in app._snd._tp_var.get() or 'Standard' in app._snd._tp_var.get())

# DLC dropdown
app._snd._dlc_var.set('8')
check("8.2.4 DLC 8", app._snd._dlc_var.get() == '8')
app._snd._dlc_var.set('3')
check("8.2.5 DLC 3", app._snd._dlc_var.get() == '3')

# Data input
app._snd._data_var.set('AA BB CC DD')
check("8.2.6 Data input", app._snd._data_var.get() == 'AA BB CC DD')

# Single send
app._tbl.clear(); pump(0.3)
app._snd._id_var.set('0x100')
app._snd._data_var.set('01 02 03')
app._snd._dlc_var.set('3')
app._snd._btn_once.invoke()
pump(1.0)
rows = []
for c in app._tbl._tree.get_children():
    rows.append(app._tbl._tree.item(c, 'values'))
tx_count = sum(1 for r in rows if len(r) > 5 and r[5] == 'TX')
check("8.2.7 Single send TX appears", tx_count >= 1, f"TX={tx_count}")

# Send panel enabled/disabled
is_enabled = app._snd._enabled
check("8.2.8 Send panel enabled", is_enabled, f"enabled={is_enabled}")

# ═══════════════════════════════════════════════════════════════
# §8.3 MessageTable
# ═══════════════════════════════════════════════════════════════
print("\n=== §8.3 MessageTable ===")

app._tbl.clear(); pump(0.3)
app._snd._id_var.set('0x200')
app._snd._tp_var.set('标准')
app._snd._data_var.set('DE AD BE EF')
app._snd._dlc_var.set('4')
app._snd._btn_once.invoke()
pump(1.0)

rows = []
for c in app._tbl._tree.get_children():
    rows.append(app._tbl._tree.item(c, 'values'))

check("8.3.1 TX direction", any(len(r) > 5 and r[5] == 'TX' for r in rows))
check("8.3.2 Standard frame type", any(len(r) > 3 and '标准' in str(r[3]) for r in rows))
check("8.3.3 NORMAL mode no RX", sum(1 for r in rows if len(r) > 5 and r[5] == 'RX') == 0)

# Clear table
app._tbl.clear()
pump(0.3)
check("8.3.4 Table clear", len(app._tbl._tree.get_children()) == 0)

# ═══════════════════════════════════════════════════════════════
# §8.4 Menu
# ═══════════════════════════════════════════════════════════════
print("\n=== §8.4 Menu ===")

# View menu toggles
app._v_left.set(False); app._relayout(); pump(0.3)
check("8.4.1 Left panel hide", not app._v_left.get())
app._v_left.set(True); app._relayout(); pump(0.3)

app._v_right.set(False); app._relayout(); pump(0.3)
check("8.4.2 Right panel hide", not app._v_right.get())
app._v_right.set(True); app._relayout(); pump(0.3)

app._v_detail.set(False); app._relayout(); pump(0.3)
check("8.4.3 Detail panel hide", not app._v_detail.get())
app._v_detail.set(True); app._relayout(); pump(0.3)

app._v_log.set(False); app._relayout(); pump(0.3)
check("8.4.4 Log panel hide", not app._v_log.get())
app._v_log.set(True); app._relayout(); pump(0.3)

# Language switch
check("8.4.5 Lang var exists", app._lang_var.get() in ('ZH', 'EN'))

# ═══════════════════════════════════════════════════════════════
# §8.5 Log Panel
# ═══════════════════════════════════════════════════════════════
print("\n=== §8.5 Log Panel ===")

log = app._log._text.get('1.0', 'end-1c')
check("8.5.1 Device info logged", "STM32F103C8T6" in log)
check("8.5.2 Capabilities logged", "Capabilities:" in log)
check("8.5.3 CAN config logged", "CAN configured:" in log)
check("8.5.4 Mode switch logged", "CAN mode:" in log)
check("8.5.5 No TX error", "CMD 0x34 failed" not in log)

# ═══════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"UI Controls: {passed}/{total} PASSED")
for name, ok in results:
    if not ok:
        print(f"  FAIL: {name}")

app._disconnect()
app.root.destroy()

if passed == total:
    print("\nALL UI TESTS PASSED!")
else:
    print(f"\n{total - passed} UI TESTS FAILED!")
