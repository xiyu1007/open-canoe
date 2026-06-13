"""波形探测 — 独立弹窗。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from gui.config import *
from gui.lang import L


class WaveformWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("open-canoe — " + L()["wave_title"])
        self.geometry("900x500"); self.minsize(600, 350)
        self._cap = False
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.withdraw)

    def _build(self) -> None:
        L_ = L()
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=0); self.rowconfigure(1, weight=1)
        tb = ttk.Frame(self)
        tb.grid(row=0, column=0, sticky=tk.EW, padx=10, pady=(10, 4))
        ttk.Label(tb, text=L_["wave_title"], font=FONT_SECTION, foreground=PRIMARY).grid(row=0, column=0)
        ttk.Label(tb, text=L_["wave_rate"]).grid(row=0, column=1, padx=(20, 4))
        self._rv = tk.StringVar(value="1 Msps")
        ttk.Combobox(tb, textvariable=self._rv, values=["100 ksps","500 ksps","1 Msps","2 Msps"],
                     state="readonly", width=10).grid(row=0, column=2, padx=(0, 10))
        ttk.Label(tb, text=L_["wave_ch"]).grid(row=0, column=3, padx=(0, 4))
        self._cv = tk.StringVar(value=L_["w_diff"])
        ttk.Combobox(tb, textvariable=self._cv, values=["CAN_H","CAN_L",L_["w_diff"]],
                     state="readonly", width=10).grid(row=0, column=4, padx=(0, 10))
        self._btn = ttk.Button(tb, text=L_["wave_cap"], command=self._toggle)
        self._btn.grid(row=0, column=5, padx=4)
        self._st = ttk.Label(tb, text=L_["wave_idle"], foreground=SECONDARY)
        self._st.grid(row=0, column=7, padx=(10, 0))

        self._cvs = tk.Canvas(self, bg=TEXT_BG, highlightthickness=0)
        self._cvs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
        self._cvs.create_text(450, 220, fill=SECONDARY, font=FONT_BODY, justify=tk.CENTER,
            text=L_["w_placeholder"])

    def _toggle(self) -> None:
        self._cap = not self._cap
        L_ = L()
        self._btn.config(text=L_["wave_pause"] if self._cap else L_["wave_cap"])
        self._st.config(text=L_["wave_capturing"] if self._cap else L_["w_paused"],
                        foreground=SUCCESS if self._cap else SECONDARY)

    def show(self) -> None:
        self.deiconify()
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")
        self.lift()
