"""报文追踪 — ttk.Treeview 彩色行，支持过滤刷新 + TX/RX 切换。"""

from __future__ import annotations

import csv, os, time, tkinter as tk
from tkinter import ttk
from gui.config import *
from gui.lang import L
from core.models import CANMessage, BusStatistics

_HISTORY_DIR = os.path.join(APP_DATA_DIR, HISTORY_DIR_NAME)


class MessageTable(ttk.Frame):
    def __init__(self, parent, max_rows=100_000, message_limit=2_000, on_open_history=None):
        super().__init__(parent)
        self._cb_hist = on_open_history
        self._max = max_rows; self._cnt = 0; self._paused = False
        self._stats = BusStatistics()
        self._f_disp: set[int] = set(); self._f_disp_mode = "off"
        self._f_msg: set[int] = set(); self._f_msg_mode = "off"
        self._show_tx = False; self._show_rx = False
        self._collapsed = False
        self._saved: list[tuple[CANMessage, bool, str]] = []  # (msg, is_tx, timestamp)
        self._collapse_cache: dict[tuple, tuple] = {}
        self._history_file: str = ""  # path to current history CSV
        self._msg_limit = message_limit  # configurable via settings.yaml
        self._build()

    def _build(self) -> None:
        L_ = L()
        # Stable internal column IDs (never change on lang switch)
        self._col_ids = ("no", "time", "id", "type", "dlc", "dir", "data")
        _cw = (50, 120, 110, 100, 50, 50, 240)
        hdr = ttk.Frame(self); hdr.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(hdr, text=L_["trace"], font=FONT_SECTION, foreground=PRIMARY).pack(side=tk.LEFT)
        self._btn_pause = ttk.Button(hdr, text=L_["pause"], command=self._toggle, width=10)
        self._btn_pause.pack(side=tk.LEFT, padx=(8, 4))
        ttk.Button(hdr, text=L_["clear"], command=self.clear, width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(hdr, text=L_["delete"], command=self._delete_selected, width=8).pack(side=tk.LEFT, padx=2)
        self._btn_collapse = ttk.Button(hdr, text="≡", command=self._toggle_collapse, width=3)
        self._btn_collapse.pack(side=tk.LEFT, padx=2)
        self._s_tx = ttk.Style(); self._s_tx.configure("TX.TButton", font=FONT_BODY)
        self._s_rx = ttk.Style(); self._s_rx.configure("RX.TButton", font=FONT_BODY)
        self._btn_tx = ttk.Button(hdr, text="TX", command=self._toggle_tx, width=4, style="TX.TButton")
        self._btn_tx.pack(side=tk.RIGHT, padx=2)
        self._btn_rx = ttk.Button(hdr, text="RX", command=self._toggle_rx, width=4, style="RX.TButton")
        self._btn_rx.pack(side=tk.RIGHT, padx=2)
        self._btn_hist2 = ttk.Button(hdr, text="Hist", command=self._open_history, width=5)
        self._btn_hist2.pack(side=tk.RIGHT, padx=(4, 8))
        self._lbl = ttk.Label(hdr, text=f"0/{self._msg_limit} {L_['msgs']}", foreground=SECONDARY, font=FONT_BODY)
        self._lbl.pack(side=tk.RIGHT, padx=(0, 8))
        tf = ttk.Frame(self); tf.pack(fill=tk.BOTH, expand=True)
        # Column headings: use internal IDs, display translated text
        col_labels = (L_["col_no"], L_["col_time"], L_["col_id"],
                      L_["col_type"], L_["col_dlc"], L_["col_ch"], L_["col_data"])
        self._tree = ttk.Treeview(tf, columns=self._col_ids, show="headings", selectmode="extended")
        for cid, w, label in zip(self._col_ids, _cw, col_labels):
            self._tree.heading(cid, text=label, anchor=tk.W)
            self._tree.column(cid, width=w, minwidth=w, stretch=(cid == "data"))
        vsb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(tf, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tf.grid_rowconfigure(0, weight=1); tf.grid_columnconfigure(0, weight=1)
        self._tree.tag_configure("std", foreground=TAG_STD)
        self._tree.tag_configure("ext", foreground=TAG_EXT)
        self._tree.tag_configure("err", foreground=TAG_ERR)
        self._tree.bind("<Control-c>", self._copy)

    def set_filter(self, ftype: str, ids: set[int], mode: str) -> None:
        if ftype == "display":
            self._f_disp = ids; self._f_disp_mode = mode
        else:
            self._f_msg = ids; self._f_msg_mode = mode
        self._rebuild()

    def add(self, msg: CANMessage, is_tx: bool = False) -> None:
        if self._paused: return
        if self._f_msg_mode == "show" and msg.arbitration_id not in self._f_msg: return
        if self._f_msg_mode == "hide" and msg.arbitration_id in self._f_msg: return
        ts = time.strftime("%H:%M:%S") + f".{int(time.time()*1000)%1000:03d}"
        self._saved.append((msg, is_tx, ts))
        # Update collapse cache incrementally (avoids O(n) scan on rebuild)
        if self._collapsed:
            key = (msg.arbitration_id, is_tx, msg.is_remote, msg.is_extended)
            self._collapse_cache[key] = (msg, is_tx, ts)
            self._rebuild()
        else:
            # Only auto-scroll if user is at/near the bottom (Bug #2 fix)
            at_bottom = self._tree.yview()[1] >= 0.95 if self._tree.get_children() else True
            self._insert_one(msg, is_tx, ts)
            if at_bottom:
                self._tree.yview_moveto(1.0)
        if msg.is_error: self._stats.record_error()
        else: self._stats.record_rx()
        self._lbl.config(text=f"{self._cnt}/{self._msg_limit} {L()['msgs']}")
        self._offload_check()
        self._prune()

    def _insert_one(self, msg: CANMessage, is_tx: bool, ts: str = "") -> None:
        if self._f_disp_mode == "show" and msg.arbitration_id not in self._f_disp: return
        if self._f_disp_mode == "hide" and msg.arbitration_id in self._f_disp: return
        if self._show_tx != self._show_rx:
            if not self._show_tx and is_tx: return
            if not self._show_rx and not is_tx: return
        self._cnt += 1; L_ = L()
        tag = "err" if msg.is_error else ("ext" if msg.is_extended else "std")
        # Internal type code (stable, used for CSV/filter)
        if msg.is_error: dtype_code = "ERR"
        elif msg.is_remote and msg.is_extended: dtype_code = "RTR_EXT"
        elif msg.is_remote: dtype_code = "RTR_STD"
        elif msg.is_extended: dtype_code = "EXT"
        else: dtype_code = "STD"
        # Display type (i18n)
        _type_map = {"STD": L_["type_std"], "EXT": L_["type_ext"], "ERR": L_["type_err"],
                     "RTR_STD": L_["type_rtr_std"], "RTR_EXT": L_["type_rtr_ext"]}
        dtype = _type_map.get(dtype_code, dtype_code)
        txrx = "TX" if is_tx else "RX"
        self._tree.insert("", tk.END, values=(
            self._cnt, ts, msg.id_str, dtype, msg.dlc, txrx, msg.data_str), tags=(tag,))

    def clear(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._saved.clear(); self._collapse_cache.clear(); self._cnt = 0
        self._lbl.config(text=f"0/{self._msg_limit} {L()['msgs']}")

    def _rebuild(self, restore_sel: bool = True) -> None:
        scroll_pos = self._tree.yview()
        sel_keys: set[tuple] = set()
        if restore_sel:
            for item in self._tree.selection():
                v = self._tree.item(item, "values")
                if v:
                    can_id = int(v[2].replace("0x", ""), 16)
                    is_tx = v[5] == "TX"
                    is_remote = "RTR" in str(v[3])
                    is_ext = v[3] in ("扩展", "EXT", "RTR EXT")
                    sel_keys.add((can_id, is_tx, is_remote, is_ext))
        self._tree.delete(*self._tree.get_children())
        self._cnt = 0
        if self._collapsed:
            # Use pre-built collapse cache (O(1)), not O(n) scan of _saved
            items = list(self._collapse_cache.values())
        else:
            items = self._saved
        # Cap visible items to prevent freeze (Bug #3)
        total = len(items)
        if total > MAX_VISIBLE:
            items = items[-MAX_VISIBLE:]
        for msg, is_tx, ts in items:
            self._insert_one(msg, is_tx, ts)
        self._lbl.config(text=f"{self._cnt}/{self._msg_limit} {L()['msgs']}"
                          + (f" (/{total})" if total > MAX_VISIBLE else ""))
        # Restore scroll position (Bug #1: don't auto-scroll to bottom)
        if scroll_pos and scroll_pos[0] > 0:
            self._tree.yview_moveto(scroll_pos[0])
        # Restore selection in collapsed mode
        if sel_keys:
            for item in self._tree.get_children():
                v = self._tree.item(item, "values")
                if v:
                    k = (int(v[2].replace("0x", ""), 16), v[5] == "TX",
                         "RTR" in str(v[3]), v[3] in ("扩展", "EXT", "RTR EXT"))
                    if k in sel_keys:
                        self._tree.selection_add(item)

    def _toggle_tx(self) -> None:
        if self._show_tx:
            self._show_tx = False; self._show_rx = False
            self._update_txrx_style()
        else:
            self._show_tx = True; self._show_rx = False
            self._update_txrx_style()
        self._rebuild()

    def _toggle_rx(self) -> None:
        if self._show_rx:
            self._show_tx = False; self._show_rx = False
            self._update_txrx_style()
        else:
            self._show_tx = False; self._show_rx = True
            self._update_txrx_style()
        self._rebuild()

    def _update_txrx_style(self) -> None:
        if self._show_tx:
            self._s_tx.configure("TX.TButton", font=(FONT_UI, 9, "bold"), foreground=SUCCESS)
        else:
            self._s_tx.configure("TX.TButton", font=FONT_BODY, foreground=TAG_MUTED)
        if self._show_rx:
            self._s_rx.configure("RX.TButton", font=(FONT_UI, 9, "bold"), foreground=SUCCESS)
        else:
            self._s_rx.configure("RX.TButton", font=FONT_BODY, foreground=TAG_MUTED)

    def _delete_selected(self) -> None:
        sel = list(self._tree.selection())
        if not sel: return
        scroll_pos = self._tree.yview()
        if self._collapsed:
            keys: set[tuple] = set()
            for item in sel:
                v = self._tree.item(item, "values")
                if v:
                    can_id = int(v[2].replace("0x",""), 16)
                    is_ext = v[3] in ("扩展", "EXT", "RTR EXT")
                    is_remote = "RTR" in v[3]
                    is_tx = v[5] == "TX"
                    keys.add((can_id, is_tx, is_remote, is_ext))
            self._saved = [m for m in self._saved
                           if (m[0].arbitration_id, m[1], m[0].is_remote, m[0].is_extended) not in keys]
            for k in keys:
                self._collapse_cache.pop(k, None)
        else:
            for item in sel:
                v = self._tree.item(item, "values")
                if v:
                    can_id = int(v[2].replace("0x",""), 16)
                    ts_str = v[1]
                    for i, (msg, is_tx, tss) in enumerate(self._saved):
                        if msg.arbitration_id == can_id and tss == ts_str:
                            self._saved.pop(i)
                            break
        self._rebuild(restore_sel=False)
        if scroll_pos and scroll_pos[0] > 0:
            self._tree.yview_moveto(scroll_pos[0])

    def refresh_lang(self) -> None:
        """Update column headings after language change."""
        L_ = L()
        labels = (L_["col_no"], L_["col_time"], L_["col_id"],
                  L_["col_type"], L_["col_dlc"], L_["col_ch"], L_["col_data"])
        for cid, label in zip(self._col_ids, labels):
            self._tree.heading(cid, text=label)
        self._lbl.config(text=f"{self._cnt}/{self._msg_limit} {L_['msgs']}")

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self._btn_collapse.config(text="-" if self._collapsed else "≡")
        # Rebuild entire collapse cache from scratch when entering collapsed mode
        if self._collapsed:
            self._collapse_cache.clear()
            for msg, is_tx, ts in self._saved:
                key = (msg.arbitration_id, is_tx, msg.is_remote, msg.is_extended)
                self._collapse_cache[key] = (msg, is_tx, ts)
        self._rebuild()

    def _offload_check(self) -> None:
        """Offload oldest half to CSV when in-memory count exceeds limit."""
        limit = self._msg_limit
        if len(self._saved) <= limit:
            return
        os.makedirs(_HISTORY_DIR, exist_ok=True)
        if not self._history_file:
            self._history_file = os.path.join(_HISTORY_DIR, "canoe_live.csv")
        # Remove oldest half for performance
        cutoff = len(self._saved) - max(limit // 2, 1)
        to_offload = self._saved[:cutoff]
        self._saved = self._saved[cutoff:]
        self._collapse_cache.clear()
        for msg, is_tx, ts in self._saved:
            key = (msg.arbitration_id, is_tx, msg.is_remote, msg.is_extended)
            self._collapse_cache[key] = (msg, is_tx, ts)
        # Overwrite live CSV with current offloaded batch (no accumulation, no junk)
        try:
            with open(self._history_file, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                for i, (msg, is_tx, ts) in enumerate(to_offload):
                    txrx = "TX" if is_tx else "RX"
                    # Use same type codes as _insert_one
                    if msg.is_error: dt = "ERR"
                    elif msg.is_remote and msg.is_extended: dt = "RTR_EXT"
                    elif msg.is_remote: dt = "RTR_STD"
                    elif msg.is_extended: dt = "EXT"
                    else: dt = "STD"
                    w.writerow([str(i + 1), ts, msg.id_str, dt,
                                str(msg.dlc), txrx, msg.data_str])
        except Exception:
            pass
        if not self._collapsed:
            self._rebuild()

    def save_history_snapshot(self) -> None:
        """Called on app close: write current in-memory messages to a final CSV.
        This is separate from the live offload file — it captures the last state."""
        if not self._saved:
            return
        os.makedirs(_HISTORY_DIR, exist_ok=True)
        snap = os.path.join(_HISTORY_DIR, "canoe_snapshot.csv")
        try:
            with open(snap, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                for msg, is_tx, ts in self._saved:
                    txrx = "TX" if is_tx else "RX"
                    if msg.is_error: dt = "ERR"
                    elif msg.is_remote and msg.is_extended: dt = "RTR_EXT"
                    elif msg.is_remote: dt = "RTR_STD"
                    elif msg.is_extended: dt = "EXT"
                    else: dt = "STD"
                    w.writerow([ts, msg.id_str, dt, str(msg.dlc), txrx, msg.data_str])
        except Exception:
            pass

    def _open_history(self) -> None:
        """Open/focus history window (shared with View menu)."""
        if self._cb_hist:
            self._cb_hist(force_open=True)
        else:
            from gui.history_window import HistoryWindow
            HistoryWindow(self.winfo_toplevel(), self._history_file,
                          current_messages=self._saved)

    @property
    def paused(self) -> bool: return self._paused
    @property
    def stats(self) -> BusStatistics: return self._stats

    def _toggle(self) -> None:
        self._paused = not self._paused; L_ = L()
        self._btn_pause.config(text=L_["resume"] if self._paused else L_["pause"])

    def _copy(self, _event) -> None:
        sel = self._tree.selection()
        if not sel: return
        lines = []
        for item in sel:
            vals = self._tree.item(item, "values")
            lines.append("\t".join(str(v) for v in vals))
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))

    def _prune(self) -> None:
        # Prune _saved if it exceeds max (collapsed mode has few tree items)
        overflow = len(self._saved) - self._max
        if overflow > 0:
            self._saved = self._saved[-self._max:]
            self._collapse_cache.clear()
            for msg, is_tx, ts in self._saved:
                key = (msg.arbitration_id, is_tx, msg.is_remote, msg.is_extended)
                self._collapse_cache[key] = (msg, is_tx, ts)
        # Prune tree items
        kids = self._tree.get_children()
        n = len(kids) - self._max
        if n > 0:
            for i in kids[:n]: self._tree.delete(i)
            self._cnt -= n
