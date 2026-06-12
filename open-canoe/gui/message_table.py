"""报文追踪 — ttk.Treeview 彩色行，支持过滤刷新 + TX/RX 切换。"""

from __future__ import annotations

import time, tkinter as tk
from tkinter import ttk
from canoe.gui.config import *
from canoe.gui.lang import L
from canoe.core.models import CANMessage, BusStatistics


class MessageTable(ttk.Frame):
    def __init__(self, parent, max_rows=100_000):
        super().__init__(parent)
        self._max = max_rows; self._cnt = 0; self._paused = False
        self._stats = BusStatistics()
        self._f_disp: set[int] = set(); self._f_disp_mode = "off"
        self._f_msg: set[int] = set(); self._f_msg_mode = "off"
        self._show_tx = False; self._show_rx = False
        self._collapsed = False
        self._saved: list[tuple[CANMessage, bool, str]] = []  # (msg, is_tx, timestamp)
        self._build()

    def _build(self) -> None:
        L_ = L()
        self._cols = (L_["col_no"], L_["col_time"], L_["col_id"],
                      L_["col_type"], L_["col_dlc"], L_["col_ch"], L_["col_data"])
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
        self._lbl = ttk.Label(hdr, text=f"0 {L_['msgs']}", foreground=SECONDARY, font=FONT_BODY)
        self._lbl.pack(side=tk.RIGHT, padx=(0, 8))
        tf = ttk.Frame(self); tf.pack(fill=tk.BOTH, expand=True)
        self._tree = ttk.Treeview(tf, columns=self._cols, show="headings", selectmode="extended")
        for col, w in zip(self._cols, _cw):
            self._tree.heading(col, text=col, anchor=tk.W)
            self._tree.column(col, width=w, minwidth=w, stretch=(col == L_["col_data"]))
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
        if self._collapsed:
            self._rebuild()
        else:
            self._insert_one(msg, is_tx, ts)
            self._tree.yview_moveto(1.0)
        if msg.is_error: self._stats.record_error()
        else: self._stats.record_rx()
        self._lbl.config(text=f"{self._cnt} {L()['msgs']}")
        self._prune()

    def _insert_one(self, msg: CANMessage, is_tx: bool, ts: str = "") -> None:
        if self._f_disp_mode == "show" and msg.arbitration_id not in self._f_disp: return
        if self._f_disp_mode == "hide" and msg.arbitration_id in self._f_disp: return
        if self._show_tx != self._show_rx:
            if not self._show_tx and is_tx: return
            if not self._show_rx and not is_tx: return
        self._cnt += 1; L_ = L()
        tag = "err" if msg.is_error else ("ext" if msg.is_extended else "std")
        if msg.is_error: dtype = L_["type_err"]
        elif msg.is_remote and msg.is_extended: dtype = "RTR EXT"
        elif msg.is_remote: dtype = "RTR STD"
        elif msg.is_extended: dtype = L_["type_ext"]
        else: dtype = L_["type_std"]
        txrx = "TX" if is_tx else "RX"
        self._tree.insert("", tk.END, values=(
            self._cnt, ts, msg.id_str, dtype, msg.dlc, txrx, msg.data_str), tags=(tag,))

    def clear(self) -> None:
        self._tree.delete(*self._tree.get_children())
        self._saved.clear(); self._cnt = 0
        self._lbl.config(text=f"0 {L()['msgs']}")

    def _rebuild(self, restore_sel: bool = True) -> None:
        scroll_pos = self._tree.yview()
        sel_keys: set[tuple] = set()
        if restore_sel:
            for sel in self._tree.selection():
                v = self._tree.item(sel, "values")
                if v:
                    can_id = int(v[2].replace("0x",""), 16)
                    is_ext = v[3] in ("扩展", "EXT", "RTR EXT")
                    is_remote = "RTR" in v[3]
                    is_tx = v[5] == "TX"
                    sel_keys.add((can_id, is_tx, is_remote, is_ext))
        self._tree.delete(*self._tree.get_children())
        self._cnt = 0
        items = self._saved
        if self._collapsed:
            seen: dict[tuple, tuple] = {}
            for msg, is_tx, ts in self._saved:
                key = (msg.arbitration_id, is_tx, msg.is_remote, msg.is_extended)
                seen[key] = (msg, is_tx, ts)
            items = list(seen.values())
        for msg, is_tx, ts in items:
            self._insert_one(msg, is_tx, ts)
        self._lbl.config(text=f"{self._cnt} {L()['msgs']}")
        if scroll_pos and scroll_pos[0] > 0:
            self._tree.yview_moveto(scroll_pos[0])
        if sel_keys:
            for item in self._tree.get_children():
                v = self._tree.item(item, "values")
                if v:
                    k = (int(v[2].replace("0x",""), 16), v[5]=="TX", "RTR" in v[3],
                         v[3] in ("扩展","EXT","RTR EXT"))
                    if k in sel_keys:
                        self._tree.selection_set(item)

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
        else:
            for item in sel:
                v = self._tree.item(item, "values")
                if v:
                    can_id = int(v[2].replace("0x",""), 16)
                    ts = v[1]
                    for i, (msg, is_tx, tss) in enumerate(self._saved):
                        if msg.arbitration_id == can_id and tss == ts:
                            self._saved.pop(i)
                            break
        self._rebuild()

    def _toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        self._btn_collapse.config(text="-" if self._collapsed else "≡")
        self._rebuild()

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
        kids = self._tree.get_children()
        n = len(kids) - self._max
        if n > 0:
            for i in kids[:n]: self._tree.delete(i)
            self._cnt -= n
            self._saved = self._saved[-self._max:]
