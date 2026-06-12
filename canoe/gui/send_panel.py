"""发送面板 — 报文编辑、周期发送、OBD-II 预设。"""

from __future__ import annotations

import time, tkinter as tk
from tkinter import ttk
from canoe.gui.config import *
from canoe.gui.lang import L
from canoe.core.models import CANMessage


class SendPanel(ttk.Frame):
    def __init__(self, parent, *, on_send=None, on_filter=None):
        super().__init__(parent, style="Card.TFrame")
        self._cb = on_send
        self._cb_filt = on_filter
        self._cycling = False; self._cycled = 0
        self._build()

    def _build(self) -> None:
        L_ = L()
        self.columnconfigure(0, weight=1)

        def s(text, row, pady=(12, 4)):
            ttk.Label(self, text=text, font=FONT_SECTION, foreground=PRIMARY).grid(
                row=row, column=0, sticky=tk.W, pady=pady)
        def b(text, row, pady=(0, 2)):
            ttk.Label(self, text=text, font=FONT_BODY, foreground=SECONDARY).grid(
                row=row, column=0, sticky=tk.W, pady=pady)

        r = 0
        s(L_["composer"], r); r += 1
        b(L_["can_id"], r); r += 1
        self._id_var = tk.StringVar(value="0x7DF")
        ttk.Entry(self, textvariable=self._id_var, font=FONT_BODY).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1

        b(L_["frame_type"], r); r += 1
        self._tp_var = tk.StringVar(value=L_["std_frame"])
        ttk.Combobox(self, textvariable=self._tp_var,
                     values=[L_["std_frame"], L_["ext_frame"]],
                     state="readonly", font=FONT_BODY).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1

        b(L_["dlc"], r); r += 1
        self._dlc_var = tk.StringVar(value="8")
        ttk.Combobox(self, textvariable=self._dlc_var,
                     values=[str(i) for i in range(1, 9)],
                     state="readonly", font=FONT_BODY).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1

        b(L_["data_hex"], r); r += 1
        self._data_var = tk.StringVar(value="02 01 00 00 00 00 00 00")
        self._data_entry = ttk.Entry(self, textvariable=self._data_var, font=FONT_BODY)
        self._data_entry.grid(row=r, column=0, sticky=tk.EW, pady=(0, 8)); r += 1
        self._data_var.trace_add("write", self._on_data_change)

        ttk.Button(self, text=L_["send_once"], command=self._send_once).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        ttk.Button(self, text=L_["send_err"], command=self._send_err).grid(
            row=r, column=0, sticky=tk.EW); r += 1

        s(L_["cycle"], r); r += 1
        b(L_["interval"], r); r += 1
        self._ivl_var = tk.StringVar(value="100")
        row = ttk.Frame(self); row.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        ttk.Entry(row, textvariable=self._ivl_var, font=FONT_BODY, width=8).pack(side=tk.LEFT)
        ttk.Label(row, text="ms", font=FONT_BODY).pack(side=tk.LEFT, padx=(4, 0))
        self._btn_cyc = ttk.Button(self, text=L_["start_cycle"], command=self._toggle_cycle)
        self._btn_cyc.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        self._cyc_lbl = ttk.Label(self, text=f"{L_['sent']} 0",
                                  foreground=SECONDARY, font=FONT_BODY)
        self._cyc_lbl.grid(row=r, column=0, sticky=tk.W); r += 1

        s(L_["filter"], r); r += 1
        self._f_id_var = tk.StringVar(value="")
        self._f_id_entry = ttk.Entry(self, textvariable=self._f_id_var, font=FONT_BODY,
                                     foreground=SECONDARY)
        self._f_id_entry.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        self._f_id_entry.insert(0, L_["filter_id"])
        self._f_id_entry.bind("<FocusIn>", self._on_filter_focus_in)
        self._f_id_entry.bind("<FocusOut>", self._on_filter_focus_out)
        self._f_id_var.trace_add("write", lambda *_: self._apply_filter())

        fm = ttk.Frame(self); fm.grid(row=r, column=0, sticky=tk.EW); r += 1
        self._f_mode = tk.StringVar(value="off")
        ttk.Radiobutton(fm, text=L_["filter_show"], variable=self._f_mode,
                        value="show", command=self._apply_filter).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(fm, text=L_["filter_hide"], variable=self._f_mode,
                        value="hide", command=self._apply_filter).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(fm, text=L_["filter_off"], variable=self._f_mode,
                        value="off", command=self._apply_filter).pack(side=tk.LEFT)

    def _on_filter_focus_in(self, _e) -> None:
        if self._f_id_var.get() == L()["filter_id"]:
            self._f_id_var.set("")
            self._f_id_entry.config(foreground=PRIMARY)

    def _on_filter_focus_out(self, _e) -> None:
        if not self._f_id_var.get().strip():
            self._f_id_var.set(L()["filter_id"])
            self._f_id_entry.config(foreground=SECONDARY)

    def _on_data_change(self, *_args) -> None:
        raw = self._data_var.get().replace(" ", "").upper()
        spaced = " ".join(raw[i:i+2] for i in range(0, len(raw), 2))
        if self._data_var.get() != spaced:
            pos = self._data_entry.index(tk.INSERT)
            self._data_var.set(spaced)
            self._data_entry.icursor(min(pos + (pos // 2), len(spaced)))

    def _apply_filter(self) -> None:
        raw = self._f_id_var.get().strip()
        if raw == L()["filter_id"]: raw = ""
        mode = self._f_mode.get()
        ids: set[int] = set()
        if raw and mode != "off":
            for p in raw.replace(",", " ").split():
                try: ids.add(int(p.replace("0x","").replace("0X",""), 16))
                except ValueError: pass
        if self._cb_filt: self._cb_filt(ids, mode)

    def _send_once(self) -> None:
        m = self._parse();
        if m and self._cb: self._cb(m)

    def _send_err(self) -> None:
        m = CANMessage(0, b"", is_error=True, timestamp_us=int(time.time() * 1_000_000))
        if self._cb: self._cb(m)

    def _toggle_cycle(self) -> None:
        L_ = L()
        if self._cycling:
            self._cycling = False; self._btn_cyc.config(text=L_["start_cycle"])
        else:
            self._cycling = True; self._cycled = 0
            self._cyc_lbl.config(text=f"{L_['sent']} 0")
            self._btn_cyc.config(text=L_["stop_cycle"]); self._tick()

    def _tick(self) -> None:
        if not self._cycling: return
        m = self._parse()
        if m and self._cb:
            self._cb(m); self._cycled += 1
            self._cyc_lbl.config(text=f"{L()['sent']} {self._cycled}")
        try: ivl = int(self._ivl_var.get())
        except ValueError: ivl = 100
        self.after(ivl, self._tick)

    def stop_cycle(self) -> None:
        self._cycling = False; self._btn_cyc.config(text=L()["start_cycle"])

    def _parse(self) -> CANMessage | None:
        try:
            can_id = int(self._id_var.get().lower().replace("0x",""), 16)
            is_ext = "扩展" in self._tp_var.get() or "Extended" in self._tp_var.get()
            dlc = int(self._dlc_var.get())
            data = bytes.fromhex(self._data_var.get().replace(" ",""))
            data = data[:8].ljust(dlc, b"\x00")[:dlc]
            return CANMessage(arbitration_id=can_id, data=data, is_extended=is_ext,
                              timestamp_us=int(time.time()*1_000_000))
        except Exception:
            return None
