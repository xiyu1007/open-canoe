"""发送面板 — 报文编辑、周期发送、OBD-II 预设。"""

from __future__ import annotations

import time, tkinter as tk
from tkinter import ttk
from gui.config import *
from gui.lang import L
from core.models import CANMessage


class SendPanel(ttk.Frame):
    def __init__(self, parent, *, on_send=None, on_filter=None):
        super().__init__(parent, style="Card.TFrame")
        self._cb = on_send
        self._cb_filt = on_filter
        self._cycling = False; self._cycled = 0
        self._enabled = True
        self._inc_val = 0
        self._build()

    def _build(self) -> None:
        L_ = L()
        self.columnconfigure(0, weight=1)

        def s(text, row, pady=(12, 4)):
            ttk.Label(self, text=text, style="Card.TLabel", font=FONT_SECTION, foreground=PRIMARY).grid(
                row=row, column=0, sticky=tk.W, pady=pady)
        def b(text, row, pady=(0, 2)):
            ttk.Label(self, text=text, style="Card.TLabel", font=FONT_BODY, foreground=SECONDARY).grid(
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
            row=r, column=0, sticky=tk.EW, pady=(0, 2)); r += 1
        self._rtr_var = tk.BooleanVar(value=False)
        self._rtr_cb = ttk.Checkbutton(self, text=L_["rtr_frame"], variable=self._rtr_var,
                                       command=self._on_rtr_toggle)
        self._rtr_cb.grid(row=r, column=0, sticky=tk.W, pady=(0, 4)); r += 1

        b(L_["dlc"], r); r += 1
        dlc_row = ttk.Frame(self, style="Card.TFrame"); dlc_row.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        self._dlc_var = tk.StringVar(value="8")
        ttk.Combobox(dlc_row, textvariable=self._dlc_var,
                     values=[str(i) for i in range(1, 9)],
                     state="readonly", font=FONT_BODY, width=4).pack(side=tk.LEFT)
        self._inc_var = tk.BooleanVar(value=False)
        self._inc_cb = ttk.Checkbutton(dlc_row, text=L_["data_inc"], variable=self._inc_var)
        self._inc_cb.pack(side=tk.LEFT, padx=(8, 0))

        b(L_["data_hex"], r); r += 1
        self._data_var = tk.StringVar(value="00 00 00 00 00 00 00 00")
        self._data_entry = ttk.Entry(self, textvariable=self._data_var, font=FONT_BODY,
                                     foreground=SECONDARY)
        self._data_entry.grid(row=r, column=0, sticky=tk.EW, pady=(0, 8)); r += 1
        self._data_entry.bind("<FocusIn>", self._on_data_focus_in)
        self._data_entry.bind("<FocusOut>", self._on_data_focus_out)
        self._dirty = False
        self._data_var.trace_add("write", self._on_data_change)

        bf = ttk.Frame(self, style="Card.TFrame"); bf.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        bf.columnconfigure(0, weight=1); bf.columnconfigure(1, weight=1)
        self._btn_once = ttk.Button(bf, text=L_["send_once"], command=self._send_once)
        self._btn_once.grid(row=0, column=0, sticky=tk.EW, padx=(0, 4))
        self._btn_err = ttk.Button(bf, text=L_["send_err"], command=self._send_err)
        self._btn_err.grid(row=0, column=1, sticky=tk.EW, padx=(4, 0))

        s(L_["cycle"], r); r += 1
        self._ivl_var = tk.StringVar(value="100")
        cyc_row = ttk.Frame(self, style="Card.TFrame"); cyc_row.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        ttk.Entry(cyc_row, textvariable=self._ivl_var, font=FONT_BODY, width=6).pack(side=tk.LEFT)
        ttk.Label(cyc_row, text="ms", style="Card.TLabel").pack(side=tk.LEFT, padx=(4, 0))
        self._btn_cyc = ttk.Button(cyc_row, text=L_["start_cycle"], command=self._toggle_cycle, width=13)
        self._btn_cyc.pack(side=tk.LEFT, padx=(10, 0))
        self._cyc_lbl = ttk.Label(self, text=f"{L_['sent']} 0",
                                  style="Card.TLabel", foreground=SECONDARY)
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
                        value="off", command=self._apply_filter).pack(side=tk.LEFT, padx=(0, 4))

        s(L_["msg_filter"], r); r += 1
        self._mf_id_var = tk.StringVar(value="")
        self._mf_id_entry = ttk.Entry(self, textvariable=self._mf_id_var, font=FONT_BODY,
                                      foreground=SECONDARY)
        self._mf_id_entry.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        self._mf_id_entry.insert(0, L_["msg_filter_id"])
        self._mf_id_entry.bind("<FocusIn>", self._on_msg_focus_in)
        self._mf_id_entry.bind("<FocusOut>", self._on_msg_focus_out)
        self._mf_id_var.trace_add("write", lambda *_: self._apply_msg_filter())

        fm2 = ttk.Frame(self); fm2.grid(row=r, column=0, sticky=tk.EW); r += 1
        self._mf_mode = tk.StringVar(value="off")
        ttk.Radiobutton(fm2, text=L_["filter_show"], variable=self._mf_mode,
                        value="show", command=self._apply_msg_filter).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(fm2, text=L_["filter_hide"], variable=self._mf_mode,
                        value="hide", command=self._apply_msg_filter).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Radiobutton(fm2, text=L_["filter_off"], variable=self._mf_mode,
                        value="off", command=self._apply_msg_filter).pack(side=tk.LEFT)

    def _do_format(self) -> None:
        if not self._dirty: return
        raw = self._data_var.get().replace(" ", "").upper()
        raw = "".join(c for c in raw if c in '0123456789ABCDEF')
        if len(raw) > 16: raw = raw[:16]
        spaced = " ".join(raw[i:i+2] for i in range(0, len(raw), 2))
        if not spaced: spaced = "00 00 00 00 00 00 00 00"
        if self._data_var.get() != spaced:
            self._data_var.set(spaced)
        self._data_entry.icursor(len(spaced))

    def _on_data_focus_in(self, _e) -> None:
        if not self._dirty:
            self._data_var.set("")
            self._data_entry.config(foreground=PRIMARY)
            self._dirty = True

    def _on_data_focus_out(self, _e) -> None:
        raw = self._data_var.get().replace(" ", "").replace(" ", "")
        if not raw:
            self._data_var.set("00 00 00 00 00 00 00 00")
            self._data_entry.config(foreground=SECONDARY)
            self._dirty = False
        else:
            raw = raw.upper()
            raw = "".join(c for c in raw if c in '0123456789ABCDEF')
            if len(raw) > 16: raw = raw[:16]
            spaced = " ".join(raw[i:i+2] for i in range(0, len(raw), 2))
            self._data_var.set(spaced)
            if self._dirty and len(raw) == 0:
                self._data_var.set("00 00 00 00 00 00 00 00")
                self._data_entry.config(foreground=SECONDARY)
                self._dirty = False

    def _on_data_change(self, *_args) -> None:
        if not self._dirty: return
        self.after_idle(self._do_format)

    def _apply_filter(self) -> None:
        raw = self._f_id_var.get().strip()
        if raw == L()["filter_id"]: raw = ""
        mode = self._f_mode.get()
        ids = self._parse_ids(raw)
        if self._cb_filt: self._cb_filt("display", ids, mode)

    def _apply_msg_filter(self) -> None:
        raw = self._mf_id_var.get().strip()
        if raw == L()["msg_filter_id"]: raw = ""
        mode = self._mf_mode.get()
        ids = self._parse_ids(raw)
        if self._cb_filt: self._cb_filt("msg", ids, mode)

    def _parse_ids(self, raw: str) -> set[int]:
        ids: set[int] = set()
        if raw:
            for p in raw.replace(",", " ").split():
                try: ids.add(int(p.replace("0x","").replace("0X",""), 16))
                except ValueError: pass
        return ids

    def _on_filter_focus_in(self, _e) -> None:
        if self._f_id_var.get() == L()["filter_id"]:
            self._f_id_var.set("")
            self._f_id_entry.config(foreground=PRIMARY)

    def _on_filter_focus_out(self, _e) -> None:
        if not self._f_id_var.get().strip():
            self._f_id_var.set(L()["filter_id"])
            self._f_id_entry.config(foreground=SECONDARY)

    def _on_msg_focus_in(self, _e) -> None:
        if self._mf_id_var.get() == L()["msg_filter_id"]:
            self._mf_id_var.set("")
            self._mf_id_entry.config(foreground=PRIMARY)

    def _on_msg_focus_out(self, _e) -> None:
        if not self._mf_id_var.get().strip():
            self._mf_id_var.set(L()["msg_filter_id"])
            self._mf_id_entry.config(foreground=SECONDARY)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._btn_once.config(state=tk.NORMAL if enabled else tk.DISABLED)
        self._btn_err.config(state=tk.NORMAL if enabled else tk.DISABLED)
        if not enabled:
            self.stop_cycle()
            self._inc_cb.config(state=tk.DISABLED)
        else:
            self._inc_cb.config(state=tk.NORMAL if not self._rtr_var.get() else tk.DISABLED)
        self._btn_cyc.config(state=tk.NORMAL if enabled else tk.DISABLED)

    def _on_rtr_toggle(self) -> None:
        if self._rtr_var.get():
            self._data_entry.config(state=tk.DISABLED, foreground=TAG_MUTED)
            self._inc_cb.config(state=tk.DISABLED)
        else:
            self._data_entry.config(state=tk.NORMAL, foreground=PRIMARY)
            self._inc_cb.config(state=tk.NORMAL)
            if self._dirty: self._do_format()

    def _send_once(self) -> None:
        if not self._enabled: return
        m = self._parse();
        if m and self._cb: self._cb(m)

    def _send_err(self) -> None:
        if not self._enabled: return
        m = CANMessage(0, b"", is_error=True, timestamp_us=int(time.time() * 1_000_000))
        if self._cb: self._cb(m)

    def _toggle_cycle(self) -> None:
        if not self._enabled: return
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
            is_rtr = self._rtr_var.get()
            dlc = int(self._dlc_var.get())
            if is_rtr:
                data = b""
            else:
                hex_str = self._data_var.get().replace(" ","")
                if len(hex_str) % 2: hex_str += "0"
                data = bytes.fromhex(hex_str)
                data = data[:8].ljust(dlc, b"\x00")[:dlc]
                if self._inc_var.get() and not is_rtr:
                    val = int.from_bytes(data, "big") + self._inc_val
                    val &= (1 << (dlc * 8)) - 1
                    data = val.to_bytes(dlc, "big")
                    self._inc_val += 1
            return CANMessage(arbitration_id=can_id, data=data, is_extended=is_ext,
                              is_remote=is_rtr, timestamp_us=int(time.time()*1_000_000))
        except Exception:
            return None
