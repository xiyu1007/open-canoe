"""日志面板 — 彩色滚动输出。"""

from __future__ import annotations

import time, tkinter as tk
from tkinter import ttk
from canoe.gui.config import *
from canoe.gui.lang import L


class LogPanel(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, style="Card.TFrame")
        self._build()

    def _build(self) -> None:
        hdr = ttk.Frame(self)
        hdr.pack(fill=tk.X)
        ttk.Label(hdr, text=L()["log"], font=FONT_SECTION, foreground=PRIMARY).pack(side=tk.LEFT)

        tf = ttk.Frame(self); tf.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        self._text = tk.Text(tf, height=4, font=FONT_MONO_9, bg="#f8fafc",
                             relief="flat", borderwidth=1, state=tk.DISABLED, wrap=tk.WORD)
        sb = ttk.Scrollbar(tf, command=self._text.yview)
        self._text.configure(yscrollcommand=sb.set)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.tag_configure("ok", foreground=SUCCESS)
        self._text.tag_configure("warn", foreground=WARNING)
        self._text.tag_configure("err", foreground=ERROR)
        self._text.tag_configure("info", foreground=SECONDARY)

    def log(self, msg: str, tag: str = "info") -> None:
        ts = time.strftime("%H:%M:%S")
        self._text.config(state=tk.NORMAL)
        self._text.insert(tk.END, f"[{ts}] {msg}\n", tag)
        self._text.see(tk.END)
        self._text.config(state=tk.DISABLED)

    def clear(self) -> None:
        self._text.config(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.config(state=tk.DISABLED)
