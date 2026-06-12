"""设备栏 — MCU、COM 端口、连接（单按钮切换）、波形、固件。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from canoe.gui.config import *
from canoe.gui.lang import L


class DeviceBar(ttk.Frame):
    def __init__(self, parent, *, on_connect=None, on_disconnect=None,
                 on_waveform=None, on_flash=None):
        super().__init__(parent, style="Card.TFrame")
        self._cb_conn = on_connect
        self._cb_disc = on_disconnect
        self._cb_wave = on_waveform or (lambda: None)
        self._cb_flash = on_flash or (lambda: None)
        self._connected = False
        self._build()

    def _build(self) -> None:
        L_ = L()
        self.columnconfigure(0, weight=1)

        def sec(text, row, pady=(10, 4)):
            ttk.Label(self, text=text, font=FONT_SECTION, foreground=PRIMARY).grid(
                row=row, column=0, sticky=tk.W, pady=pady)

        def sub(text, row, pady=(0, 2)):
            ttk.Label(self, text=text, font=FONT_BODY, foreground=SECONDARY).grid(
                row=row, column=0, sticky=tk.W, pady=pady)

        r = 0
        sec(L_["mcu"], r); r += 1
        self._mcu_var = tk.StringVar(value="STM32F103C8T6")
        ttk.Combobox(self, textvariable=self._mcu_var,
                     values=["STM32F103C8T6", "STM32F407VET6"],
                     state="readonly", font=FONT_BODY).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 8)); r += 1

        sec(L_["com_port"], r); r += 1
        pf = ttk.Frame(self); pf.grid(row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        pf.columnconfigure(0, weight=1)
        self._port_var = tk.StringVar(value="auto")
        ports = self._scan()
        self._port_cb = ttk.Combobox(pf, textvariable=self._port_var,
                                     values=["auto"] + ports, state="readonly", font=FONT_BODY)
        self._port_cb.grid(row=0, column=0, sticky=tk.EW)
        ttk.Button(pf, text="⟳", width=3, command=self._refresh_ports).grid(row=0, column=1, padx=(4, 0))

        sec(L_["connection"], r); r += 1
        self._status_lbl = ttk.Label(self, text=L_["disconnected"],
                                     foreground=SECONDARY, font=FONT_BODY)
        self._status_lbl.grid(row=r, column=0, sticky=tk.W); r += 1
        self._btn = ttk.Button(self, text=L_["connect"], command=self._toggle)
        self._btn.grid(row=r, column=0, sticky=tk.EW, pady=(4, 8)); r += 1

        sec(L_["can_settings"], r); r += 1
        sub(L_["bitrate"], r); r += 1
        self._br_var = tk.StringVar(value="500 kbps")
        ttk.Combobox(self, textvariable=self._br_var, values=BITRATES,
                     state="readonly", font=FONT_BODY).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 4)); r += 1
        self._silent_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text=L_["silent"], variable=self._silent_var).grid(
            row=r, column=0, sticky=tk.W, pady=(0, 8)); r += 1

        sec(L_["waveform"], r); r += 1
        ttk.Button(self, text=L_["open_waveform"], command=self._cb_wave).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 8)); r += 1

        sec(L_["firmware"], r); r += 1
        ttk.Button(self, text=L_["flash_fw"], command=self._cb_flash).grid(
            row=r, column=0, sticky=tk.EW, pady=(0, 8)); r += 1

        sec(L_["filter"], r); r += 1
        ttk.Label(self, text=L_["no_filter"], foreground=SECONDARY, font=FONT_BODY).grid(
            row=r, column=0, sticky=tk.W)

    def _scan(self) -> list[str]:
        from canoe.core.transport import list_serial_ports
        return [p.port for p in list_serial_ports()]

    def _refresh_ports(self) -> None:
        self._port_cb["values"] = ["auto"] + self._scan()

    @property
    def selected_mcu(self) -> str: return self._mcu_var.get()
    @property
    def selected_port(self) -> str: return self._port_var.get()
    @property
    def selected_bitrate(self) -> str: return self._br_var.get()
    @property
    def silent_mode(self) -> bool: return self._silent_var.get()
    @property
    def is_connected(self) -> bool: return self._connected

    def set_connecting(self) -> None:
        self._connected = False; L_ = L()
        self._status_lbl.config(text=L_["connecting"], foreground=WARNING)
        self._btn.config(state=tk.DISABLED)

    def set_connected(self, port: str = "") -> None:
        self._connected = True; L_ = L()
        self._status_lbl.config(text=f"{L_['connected']} — {port}", foreground=SUCCESS)
        self._btn.config(text=L_["disconnect"], state=tk.NORMAL)

    def set_disconnected(self) -> None:
        self._connected = False; L_ = L()
        self._status_lbl.config(text=L_["disconnected"], foreground=SECONDARY)
        self._btn.config(text=L_["connect"], state=tk.NORMAL)

    def _toggle(self) -> None:
        if self._connected: self._cb_disc()
        else: self._cb_conn()
