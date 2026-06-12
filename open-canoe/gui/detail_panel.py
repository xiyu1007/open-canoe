"""信号详情 — 选中报文的原始+解码信息。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from gui.config import *
from gui.lang import L
from core.models import CANMessage


class DetailPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style="Card.TFrame")
        self._build()

    def _build(self) -> None:
        L_ = L()
        self.columnconfigure(0, weight=1); self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text=L_["raw_msg"], font=FONT_SECTION,
                  foreground=SECONDARY).grid(row=0, column=0, sticky=tk.W, pady=(0, 4))
        ttk.Label(self, text=L_["decoded"], font=FONT_SECTION,
                  foreground=SECONDARY).grid(row=0, column=1, sticky=tk.W, pady=(0, 4))

        self._raw = tk.Text(self, height=5, font=FONT_BODY, bg=TEXT_BG,
                            fg=PRIMARY, relief="flat", borderwidth=0, state=tk.DISABLED)
        self._raw.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(2, 0))
        self._dec = tk.Text(self, height=5, font=FONT_BODY, bg=TEXT_BG,
                            fg=PRIMARY, relief="flat", borderwidth=0, state=tk.DISABLED)
        self._dec.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(2, 0))

    def show(self, msg: CANMessage) -> None:
        L_ = L()
        dtype = L_["type_ext"] if msg.is_extended else L_["type_std"]
        if msg.is_error: dtype = L_["type_err"]
        us = msg.timestamp_us
        ts_str = f"{us//3600000000:02d}:{(us//60000000)%60:02d}:{(us//1000000)%60:02d}.{(us//1000)%1000:03d}"
        raw = (f"{L_['d_id']}     {msg.id_str}\n"
               f"{L_['d_type']}   {dtype}\n"
               f"{L_['d_dlc']}    {msg.dlc}\n"
               f"{L_['d_data']}   {msg.data_str}\n"
               f"{L_['d_time']}   {ts_str}")
        self._raw.config(state=tk.NORMAL); self._raw.delete("1.0", tk.END)
        self._raw.insert("1.0", raw); self._raw.config(state=tk.DISABLED)

        if msg.is_error:
            dec = L_["d_err"]
        elif msg.dlc == 0:
            dec = L_["d_empty"]
        else:
            d = msg.data[:msg.dlc]
            lines = [f"hex: {msg.data_str}"]
            if msg.dlc >= 1: lines.append(f"uint8:    [{', '.join(str(b) for b in d)}]")
            if msg.dlc >= 2: lines.append(f"uint16 LE: {int.from_bytes(d[:2], 'little')}")
            if msg.dlc >= 2: lines.append(f"uint16 BE: {int.from_bytes(d[:2], 'big')}")
            if msg.dlc >= 4: lines.append(f"uint32 LE: {int.from_bytes(d[:4], 'little')}")
            dec = "\n".join(lines)
        self._dec.config(state=tk.NORMAL); self._dec.delete("1.0", tk.END)
        self._dec.insert("1.0", dec); self._dec.config(state=tk.DISABLED)
