"""报文追踪 — ttk.Treeview 彩色行。"""

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
        self._filt_ids: set[int] = set(); self._filt_mode = "off"
        self._build()

    def _build(self) -> None:
        L_ = L()
        self._cols = (L_["col_no"], L_["col_time"], L_["col_id"],
                      L_["col_type"], L_["col_dlc"], L_["col_data"], L_["col_ch"])
        _cw = (50, 130, 100, 55, 45, 240, 40)

        hdr = ttk.Frame(self); hdr.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(hdr, text=L_["trace"], font=FONT_SECTION, foreground=PRIMARY).pack(side=tk.LEFT)
        self._btn_pause = ttk.Button(hdr, text=L_["pause"], command=self._toggle, width=8)
        self._btn_pause.pack(side=tk.LEFT, padx=(8, 4))
        ttk.Button(hdr, text=L_["clear"], command=self.clear, width=7).pack(side=tk.LEFT, padx=2)
        self._lbl = ttk.Label(hdr, text=f"0 {L_['msgs']}", foreground=SECONDARY, font=FONT_BODY)
        self._lbl.pack(side=tk.RIGHT)

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

    def set_filter(self, ids: set[int], mode: str) -> None:
        self._filt_ids = ids; self._filt_mode = mode

    def add(self, msg: CANMessage) -> None:
        if self._paused: return
        if self._filt_mode == "show" and msg.arbitration_id not in self._filt_ids: return
        if self._filt_mode == "hide" and msg.arbitration_id in self._filt_ids: return
        self._cnt += 1; L_ = L()
        ts = time.strftime("%H:%M:%S") + f".{int(time.time()*1000)%1000:03d}"
        tag = "err" if msg.is_error else ("ext" if msg.is_extended else "std")
        dtype = L_["type_err"] if msg.is_error else (L_["type_ext"] if msg.is_extended else L_["type_std"])
        self._tree.insert("", tk.END, values=(
            self._cnt, ts, msg.id_str, dtype, msg.dlc, msg.data_str, str(msg.channel)), tags=(tag,))
        self._tree.yview_moveto(1.0)
        if msg.is_error: self._stats.record_error()
        else: self._stats.record_rx()
        self._lbl.config(text=f"{self._cnt} {L_['msgs']}")
        self._prune()

    def clear(self) -> None:
        for i in self._tree.get_children(): self._tree.delete(i)
        self._cnt = 0; self._lbl.config(text=f"0 {L()['msgs']}")

    @property
    def paused(self) -> bool: return self._paused
    @property
    def stats(self) -> BusStatistics: return self._stats

    def _toggle(self) -> None:
        self._paused = not self._paused
        L_ = L()
        self._btn_pause.config(text=L_["resume"] if self._paused else L_["pause"])

    def _prune(self) -> None:
        kids = self._tree.get_children()
        n = len(kids) - self._max
        if n > 0:
            for i in kids[:n]: self._tree.delete(i)
