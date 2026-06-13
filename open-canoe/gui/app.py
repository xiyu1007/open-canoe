"""open-canoe 主窗口 — 简洁布局，可折叠面板自动重排。"""

from __future__ import annotations

import os, tkinter as tk
from tkinter import ttk, messagebox
import threading, queue, time

from gui.config import load_config
from core.models import CANMessage
from core.transport import (
    SerialTransport,
    TransportError,
    detect_and_connect,
    list_serial_ports,
)
from core.protocol import (
    Command,
    Frame,
    encode,
    pack_can_send_frame,
    pack_can_set_baudrate,
    pack_can_set_mode,
    unpack_can_frame_up,
    unpack_device_info,
    unpack_capabilities,
    unpack_ack,
    unpack_error_notify,
    CAN_MODE_NORMAL,
    CAN_MODE_LISTEN_ONLY,
    CAN_MODE_LOOPBACK,
    CAN_MODE_LOOPBACK_SILENT,
    ERR_NONE,
    ERR_CAN_TX_FAILED,
    ERR_ADC_NOT_AVAILABLE,
    ERROR_MESSAGES,
)

from gui.config import *
from gui.lang import L, set_lang, lang_code
from gui.message_table import MessageTable
from gui.device_bar import DeviceBar
from gui.send_panel import SendPanel
from gui.detail_panel import DetailPanel
from gui.log_panel import LogPanel
from gui.waveform_window import WaveformWindow


class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.settings = load_config()
        self._tr = None
        self._wave = None
        self._q: queue.Queue = queue.Queue()

        self._v_detail = tk.BooleanVar(value=True)
        self._v_log    = tk.BooleanVar(value=True)
        self._v_left   = tk.BooleanVar(value=True)
        self._v_right  = tk.BooleanVar(value=True)
        self._v_hist   = tk.BooleanVar(value=False)

        # Device state
        self._dev_info: dict = {}
        self._caps: dict = {}
        self._can_active = False

        self._build_style()
        self._build_layout()
        self._build_menu()
        self._center()
        self._poll()

    def _build_style(self) -> None:
        L_ = L()
        self.root.title(L_["title"])
        self.root.configure(bg=BG)
        self.root.minsize(1100, 680)
        self.root.geometry("1400x820")

        s = ttk.Style()
        for t_ in ("vista", "winnative", "xpnative", "clam"):
            try: s.theme_use(t_); break
            except tk.TclError: continue

        s.configure("TFrame", background=BG)
        s.configure("Card.TFrame", background=CARD, relief="flat")
        s.configure("Title.TLabel", font=FONT_TITLE, foreground=PRIMARY, background=BG)
        s.configure("Section.TLabel", font=FONT_SECTION, foreground=PRIMARY, background=CARD)
        s.configure("Hint.TLabel", font=FONT_HINT, foreground=TAG_MUTED, background=BG)
        s.configure("TLabel", background=BG, font=FONT_BODY, foreground=PRIMARY)
        s.configure("Card.TLabel", background=CARD, font=FONT_BODY, foreground=PRIMARY)
        s.configure("TButton", font=FONT_BODY)
        s.configure("TEntry", font=FONT_BODY)
        s.configure("TCombobox", font=FONT_BODY)
        s.configure("TCheckbutton", font=FONT_BODY, background=CARD)
        s.configure("Card.TRadiobutton", font=FONT_BODY, background=CARD)
        s.configure("Treeview", font=FONT_BODY, rowheight=22)
        s.configure("Treeview.Heading", font=FONT_SECTION)

    def _build_layout(self) -> None:
        L_ = L()
        outer = ttk.Frame(self.root, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)
        # tf = ttk.Frame(outer)
        # tf.pack(fill=tk.X, pady=(0, 8))
        # ttk.Label(tf, text=L_["title"], style="Title.TLabel").pack(side=tk.LEFT)
        self._v_pane = ttk.PanedWindow(outer, orient=tk.VERTICAL)
        self._v_pane.pack(fill=tk.BOTH, expand=True)

        self._h_pane = ttk.PanedWindow(self._v_pane, orient=tk.HORIZONTAL)
        self._v_pane.add(self._h_pane, weight=1)

        # 左栏
        self._frame_left = ttk.Frame(self._h_pane)
        self._card_left = ttk.Frame(self._frame_left, style="Card.TFrame", padding=14)
        self._card_left.pack(fill=tk.BOTH, expand=True)
        self._dev = DeviceBar(
            self._card_left,
            on_connect=self._connect_async,
            on_disconnect=self._disconnect,
            on_waveform=self._open_waveform,
            on_flash=self._flash_dialog,
            on_silent=self._on_silent,
            on_loopback=self._on_loopback,
        )
        self._dev.pack(fill=tk.BOTH, expand=True)
        self._h_pane.add(self._frame_left, weight=0)

        # 中栏
        self._ctr_pane = ttk.PanedWindow(self._h_pane, orient=tk.VERTICAL)

        self._frame_trace = ttk.Frame(self._ctr_pane)
        self._card_trace = ttk.Frame(self._frame_trace, style="Card.TFrame", padding=14)
        self._card_trace.pack(fill=tk.BOTH, expand=True)
        self._card_trace.rowconfigure(0, weight=1); self._card_trace.columnconfigure(0, weight=1)
        self._hist_win = None
        self._tbl = MessageTable(self._card_trace, max_rows=self.settings.get("ui", {}).get("max_log_lines", 100000),
                                 message_limit=self.settings.get("ui", {}).get("message_limit", 2000),
                                 on_open_history=self._toggle_history)
        self._tbl.pack(fill=tk.BOTH, expand=True)
        self._ctr_pane.add(self._frame_trace, weight=1)

        self._frame_det = ttk.Frame(self._ctr_pane)
        self._card_det = ttk.Frame(self._frame_det, style="Card.TFrame", padding=14)
        self._card_det.pack(fill=tk.BOTH, expand=True)
        self._det = DetailPanel(self._card_det)
        self._det.pack(fill=tk.BOTH, expand=True)

        self._h_pane.add(self._ctr_pane, weight=1)

        # 右栏
        self._frame_right = ttk.Frame(self._h_pane)
        self._card_right = ttk.Frame(self._frame_right, style="Card.TFrame", padding=14)
        self._card_right.pack(fill=tk.BOTH, expand=True)
        self._snd = SendPanel(self._card_right, on_send=self._on_send, on_filter=self._on_filter)
        self._snd.pack(fill=tk.BOTH, expand=True)
        self._snd.set_enabled(False)  # disabled until connected
        self._h_pane.add(self._frame_right, weight=0)

        # 日志
        self._frame_log = ttk.Frame(self._v_pane)
        self._card_log = ttk.Frame(self._frame_log, style="Card.TFrame", padding=14)
        self._card_log.pack(fill=tk.BOTH, expand=True)
        self._log = LogPanel(self._card_log)
        self._log.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        sf = ttk.Frame(outer)
        sf.pack(fill=tk.X, pady=(4, 0))
        self._status_var = tk.StringVar(value=L_["disconnected"])
        ttk.Label(sf, textvariable=self._status_var, font=FONT_HINT,
                  foreground=TAG_MUTED).pack(side=tk.LEFT)
        self._rate_var = tk.StringVar(value="RX: 0 msg/s  |  TX: 0  |  错误: 0")
        ttk.Label(sf, textvariable=self._rate_var, font=FONT_HINT,
                  foreground=TAG_MUTED).pack(side=tk.RIGHT)

        self._tbl._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._relayout()

    def _relayout(self) -> None:
        for w in self._h_pane.panes():
            self._h_pane.forget(w)
        if self._v_left.get():
            self._h_pane.add(self._frame_left, weight=0)
        self._h_pane.add(self._ctr_pane, weight=1)
        if self._v_right.get():
            self._h_pane.add(self._frame_right, weight=0)

        for w in self._ctr_pane.panes():
            self._ctr_pane.forget(w)
        self._ctr_pane.add(self._frame_trace, weight=1)
        if self._v_detail.get():
            self._ctr_pane.add(self._frame_det, weight=0)

        for w in self._v_pane.panes():
            self._v_pane.forget(w)
        self._v_pane.add(self._h_pane, weight=1)
        if self._v_log.get():
            self._v_pane.add(self._frame_log, weight=0)

    def _build_menu(self) -> None:
        L_ = L()
        mb = tk.Menu(self.root, font=FONT_BODY, tearoff=0)
        self.root.config(menu=mb)  # replaces old menu (old one gets garbage collected)
        dm = tk.Menu(mb, tearoff=0)
        dm.add_command(label=L_["menu_connect"], command=self._connect_async)
        dm.add_command(label=L_["menu_disconnect"], command=self._disconnect)
        dm.add_separator()
        dm.add_command(label=L_["menu_exit"], command=self._on_close)
        mb.add_cascade(label=L_["menu_device"], menu=dm)
        vm = tk.Menu(mb, tearoff=0)
        vm.add_command(label=L_["menu_clear_msgs"], command=self._clear)
        vm.add_command(label=L_["menu_clear_log"], command=self._log.clear)
        vm.add_separator()
        vm.add_command(label=L_["menu_waveform"], command=self._open_waveform)
        vm.add_separator()
        vm.add_checkbutton(label=L_["menu_device_bar"], variable=self._v_left, command=self._relayout)
        vm.add_checkbutton(label=L_["menu_send"], variable=self._v_right, command=self._relayout)
        vm.add_checkbutton(label=L_["menu_detail"], variable=self._v_detail, command=self._relayout)
        vm.add_checkbutton(label=L_["menu_log"], variable=self._v_log, command=self._relayout)
        vm.add_separator()
        vm.add_checkbutton(label=L_.get("menu_history", "History Messages"),
                           variable=self._v_hist, command=self._toggle_history)
        mb.add_cascade(label=L_["menu_view"], menu=vm)
        sm = tk.Menu(mb, tearoff=0)
        lm = tk.Menu(sm, tearoff=0)
        self._lang_var = tk.StringVar(value=lang_code())
        lm.add_radiobutton(label="中文", variable=self._lang_var, value="ZH",
                           command=lambda: self._switch_lang("ZH"))
        lm.add_radiobutton(label="English", variable=self._lang_var, value="EN",
                           command=lambda: self._switch_lang("EN"))
        sm.add_cascade(label=L_["menu_lang"], menu=lm)
        mb.add_cascade(label=L_["menu_settings"], menu=sm)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label=L_["menu_about"], command=self._about)
        mb.add_cascade(label=L_["menu_help"], menu=hm)

    def _switch_lang(self, code: str) -> None:
        set_lang(code)  # saves preference, applies on next start
        messagebox.showinfo(L()["menu_lang"],
            "请重启程序使语言设置生效。\nRestart to apply language change.")

    def _toggle_history(self, force_open: bool = False) -> None:
        """Open/close/focus the shared history window (Hist button + View menu)."""
        from gui.history_window import HistoryWindow
        if force_open:
            self._v_hist.set(True)  # sync checkbox when Hist button pressed
        if self._v_hist.get():
            # Open or focus existing
            if self._hist_win and self._hist_win.winfo_exists():
                self._hist_win.deiconify()
                self._hist_win.lift()
                self._hist_win.focus_force()
                return
            self._hist_win = HistoryWindow(self.root, self._tbl._history_file,
                                           current_messages=self._tbl._saved)
            def _on_close():
                self._v_hist.set(False)
                if self._hist_win:
                    self._hist_win.destroy()
                    self._hist_win = None
            self._hist_win.protocol("WM_DELETE_WINDOW", _on_close)
        else:
            if self._hist_win and self._hist_win.winfo_exists():
                self._hist_win.destroy()
                self._hist_win = None

    # ── Connection ────────────────────────────────────────────────

    def _connect_async(self) -> None:
        if self._tr is not None: self._disconnect(); return
        port = self._dev.selected_port
        mcu = self._dev.selected_mcu
        self._dev.set_connecting()
        self._status_var.set(L()["connecting"])
        threading.Thread(target=self._conn_thread, args=(port, mcu), daemon=True).start()

    def _conn_thread(self, port: str, mcu: str) -> None:
        try:
            tr, hb = detect_and_connect(
                port=port if port.upper() != "AUTO" else None,
                baudrate=self.settings.get("transport", {}).get("serial_baud", 115200),
            )
            self._q.put(("ok", tr, hb))
        except TransportError as e:
            self._q.put(("err", str(e)))
        except Exception as e:
            self._q.put(("err", f"{L()['conn_failed']}: {e}"))

    def _on_connected(self, tr, hb: dict) -> None:
        """Called from poll() when connection + heartbeat succeeds."""
        L_ = L()
        self._tr = tr
        self._dev_info = hb
        self._dev.set_connected(self._tr.info.port)
        # Update port dropdown from "auto" to the actual port
        self._dev._port_var.set(self._tr.info.port)
        # Enable send panel on connection
        self._snd.set_enabled(not self._dev.silent_mode)
        model = hb.get("mcu_model", "Unknown")
        fw = hb.get("fw_version", "?")
        self._status_var.set(
            f"{L_['connected']} — {self._tr.info.port}  |  {model}  FW v{fw}"
        )
        self._log.log(
            f"Device: {model}  FW: v{fw}  Port: {self._tr.info.port}", "ok"
        )

        # Query capabilities
        try:
            self._tr.write(encode(Command.GET_CAPABILITIES))
        except Exception:
            pass

        # Query device info
        try:
            self._tr.write(encode(Command.GET_INFO))
        except Exception:
            pass

        # Configure CAN after short delay (allow responses to arrive)
        self.root.after(300, self._configure_can)

    def _configure_can(self) -> None:
        """Send CAN configuration to hardware after capabilities are known."""
        if not self._tr or not self._tr.is_connected:
            return

        # Parse bitrate
        br_str = self._dev.selected_bitrate.replace(" kbps", "").replace(" Mbps", "")
        baudrate = int(br_str) * 1000
        if br_str == "1":
            baudrate = 1000000

        # Determine mode based on silent + loopback checkboxes
        silent = self._dev.silent_mode
        loopback = self._dev.loopback_mode
        if loopback and silent:
            mode = CAN_MODE_LOOPBACK_SILENT
        elif loopback:
            mode = CAN_MODE_LOOPBACK
        elif silent:
            mode = CAN_MODE_LISTEN_ONLY
        else:
            mode = CAN_MODE_NORMAL

        try:
            self._tr.write(encode(Command.CAN_SET_BAUDRATE,
                                   pack_can_set_baudrate(baudrate, 0)))
            self._tr.write(encode(Command.CAN_SET_MODE,
                                   pack_can_set_mode(mode, 0)))
            self._tr.write(encode(Command.CAN_START_LISTEN))
            self._can_active = True
            self._log.log(
                f"CAN configured: {baudrate//1000}kbps, mode={mode}", "info"
            )
        except Exception as e:
            self._log.log(f"CAN config failed: {e}", "err")

    def _disconnect(self) -> None:
        if self._tr:
            try:
                if self._can_active:
                    self._tr.write(encode(Command.CAN_STOP_LISTEN))
            except Exception:
                pass
            try:
                self._tr.disconnect()
            except Exception:
                pass
            self._tr = None
        self._can_active = False
        self._dev_info = {}
        self._caps = {}
        self._dev.set_disconnected()
        self._snd.set_enabled(False)
        self._status_var.set(L()["disconnected"])

    # ── Poll Loop ─────────────────────────────────────────────────

    def _poll(self) -> None:
        """Main poll: handle async connection results + incoming frames."""
        try:
            while True:
                kind, *data = self._q.get_nowait()
                L_ = L()
                if kind == "ok":
                    tr, hb = data[0], data[1]
                    self._on_connected(tr, hb)
                elif kind == "err":
                    msg = data[0]
                    messagebox.showwarning(L_["no_device"], msg)
                    self._log.log(msg, "err")
                    self._dev.set_disconnected()
                    self._status_var.set(L_["disconnected"])
        except queue.Empty:
            pass

        # Process incoming frames from transport
        self._poll_incoming()

        self.root.after(200, self._poll)

    def _poll_incoming(self) -> None:
        """Read and dispatch incoming protocol frames."""
        if self._tr is None:
            return
        try:
            frames = self._tr.incoming()
        except Exception:
            return
        for f in frames:
            self._handle_frame(f)

    def _handle_frame(self, f: Frame) -> None:
        """Route an incoming protocol frame to the correct handler."""
        cmd = f.command
        if cmd == Command.CAN_FRAME_UP:
            self._handle_can_frame(f)
        elif cmd == Command.ACK:
            self._handle_ack(f)
        elif cmd == Command.NACK:
            self._log.log("NACK received", "warn")
        elif cmd == Command.ERROR_NOTIFY:
            self._handle_error(f)
        elif cmd == Command.CAPABILITIES_RESP:
            self._handle_capabilities(f)
        elif cmd == Command.INFO_RESPONSE:
            self._handle_info(f)
        elif cmd == Command.STATUS_RESPONSE:
            pass  # Status poll response — currently unused
        elif cmd == Command.DEVICE_HEARTBEAT:
            pass  # Only expected during connect; ignore in normal operation
        elif cmd == Command.ADC_DATA_UP:
            self._handle_adc_data(f)
        elif cmd == Command.ADC_STATUS_RESP:
            pass  # Currently unused

    def _handle_can_frame(self, f: Frame) -> None:
        """Decode and display an incoming CAN frame."""
        try:
            d = unpack_can_frame_up(f.payload)
        except Exception:
            return
        msg = CANMessage(
            arbitration_id=d["arbitration_id"],
            data=d["data"],
            is_extended=d["is_extended"],
            is_error=d["is_error"],
            is_remote=d["is_remote"],
            timestamp_us=d["timestamp_us"],
            channel=d["channel"],
        )
        self._tbl.add(msg, is_tx=False)
        self._tbl.stats.record_rx()

    def _handle_ack(self, f: Frame) -> None:
        """Handle ACK frame."""
        try:
            ack = unpack_ack(f.payload)
        except Exception:
            return
        if ack["error_code"] == ERR_NONE:
            return  # Success — silent
        error_msg = ERROR_MESSAGES.get(ack["error_code"],
                                        f"Error 0x{ack['error_code']:02X}")
        ack_cmd = ack["ack_cmd"]
        self._log.log(f"CMD 0x{ack_cmd:02X} failed: {error_msg}", "err")

    def _handle_error(self, f: Frame) -> None:
        """Handle error notification from firmware."""
        try:
            err = unpack_error_notify(f.payload)
        except Exception:
            return
        self._log.log(
            f"[{err['source']}] {err['error_name']}", "err"
        )
        self._tbl.stats.record_error()

    def _handle_capabilities(self, f: Frame) -> None:
        """Cache device capabilities."""
        try:
            self._caps = unpack_capabilities(f.payload)
            self._log.log(
                f"Capabilities: ADC={self._caps['has_adc']}, "
                f"USB_CDC={self._caps['has_usb_cdc']}, "
                f"CAN ch={self._caps['can_channel_count']}",
                "info",
            )
        except Exception:
            pass

    def _handle_info(self, f: Frame) -> None:
        """Cache device info."""
        try:
            info = unpack_device_info(f.payload)
            self._dev_info.update(info)
        except Exception:
            pass

    def _handle_adc_data(self, f: Frame) -> None:
        """Feed ADC data to waveform window."""
        if self._wave is not None:
            try:
                self._wave.feed_adc_data(f.payload)
            except Exception:
                pass

    # ── UI Callbacks ──────────────────────────────────────────────

    def _on_silent(self, silent: bool) -> None:
        self._snd.set_enabled(not silent)
        self._update_can_mode()

    def _on_loopback(self, loopback: bool) -> None:
        self._update_can_mode()

    def _update_can_mode(self) -> None:
        """Send the current silent + loopback state to firmware."""
        if not self._tr or not self._tr.is_connected:
            return
        silent = self._dev.silent_mode
        loopback = self._dev.loopback_mode
        if loopback and silent:
            mode = CAN_MODE_LOOPBACK_SILENT
        elif loopback:
            mode = CAN_MODE_LOOPBACK
        elif silent:
            mode = CAN_MODE_LISTEN_ONLY
        else:
            mode = CAN_MODE_NORMAL
        try:
            self._tr.write(encode(Command.CAN_SET_MODE,
                                   pack_can_set_mode(mode, 0)))
            mode_names = {0: "normal", 1: "listen-only",
                          2: "loopback", 3: "loopback+silent"}
            self._log.log(f"CAN mode: {mode_names.get(mode, str(mode))}", "info")
        except Exception as e:
            self._log.log(f"Mode change failed: {e}", "err")

    def _on_filter(self, ftype: str, ids: set[int], mode: str) -> None:
        self._tbl.set_filter(ftype, ids, mode)

    def _on_send(self, msg: CANMessage) -> None:
        # Local display always
        self._tbl.add(msg, is_tx=True)
        L_ = L()
        if msg.is_error:
            self._log.log(L_["send_err_log"], "err")
        elif msg.is_remote:
            self._log.log(f"{L_['send_rtr_log']} ID={msg.id_str}", "info")

        # Send to hardware if connected
        if self._tr and self._tr.is_connected:
            try:
                payload = pack_can_send_frame(
                    can_id=msg.arbitration_id,
                    dlc=msg.dlc,
                    is_extended=msg.is_extended,
                    is_remote=msg.is_remote,
                    channel=msg.channel,
                    data=msg.data,
                )
                self._tr.write(encode(Command.CAN_SEND_FRAME, payload))
                self._tbl.stats.record_tx()
            except Exception as e:
                self._log.log(f"{L_['send_fail']}: {e}", "err")

    def _on_select(self, _event) -> None:
        sel = self._tbl._tree.selection()
        if not sel: return
        vals = self._tbl._tree.item(sel[0], "values")
        if not vals: return
        try:
            can_id = int(vals[2].replace("0x", ""), 16)
            L_ = L()
            is_ext = vals[3] == L_["type_ext"]
            is_err = vals[3] == L_["type_err"]
            data = bytes.fromhex(vals[6].replace(" ", ""))
            ts_str = vals[1]
            ts_us = 0
            try:
                parts = ts_str.split(".")
                hms = parts[0].split(":")
                secs = int(hms[0])*3600 + int(hms[1])*60 + int(hms[2])
                ms = int(parts[1]) if len(parts) > 1 else 0
                ts_us = secs * 1_000_000 + ms * 1000
            except Exception:
                pass
            self._det.show(CANMessage(
                arbitration_id=can_id, data=data, is_extended=is_ext, is_error=is_err,
                timestamp_us=ts_us))
        except Exception:
            pass

    def _open_waveform(self) -> None:
        if self._wave is None: self._wave = WaveformWindow(self.root)
        self._wave.show()

    def _flash_dialog(self) -> None:
        L_ = L()
        dlg = tk.Toplevel(self.root); dlg.title(L_["flash_title"])
        dlg.geometry("500x380"); dlg.resizable(False, False)
        dlg.transient(self.root); dlg.grab_set()
        dlg.update_idletasks()
        x = (dlg.winfo_screenwidth() - 500) // 2
        y = (dlg.winfo_screenheight() - 380) // 2
        dlg.geometry(f"+{x}+{y}")
        f = ttk.Frame(dlg, padding=16); f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text=L_["flash_select"], font=FONT_SECTION).pack(anchor=tk.W)
        mcu = tk.StringVar(value="STM32F103C8T6")
        ttk.Radiobutton(f, text=L_["flash_info_f103"],
                        variable=mcu, value="STM32F103C8T6").pack(anchor=tk.W, pady=(4, 8))
        ttk.Radiobutton(f, text=L_["flash_info_f407"],
                        variable=mcu, value="STM32F407VET6").pack(anchor=tk.W, pady=(0, 8))
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)
        txt = tk.Text(f, height=8, font=FONT_MONO_9, bg=TEXT_BG, relief="flat", borderwidth=1)
        txt.pack(fill=tk.BOTH, expand=True, pady=(4, 8)); txt.insert("1.0", L_["flash_steps"])
        txt.config(state=tk.DISABLED)
        ttk.Button(f, text="OK", command=dlg.destroy).pack(side=tk.RIGHT)

    def _refresh(self) -> None:
        s = self._tbl.stats
        self._rate_var.set(f"RX: {s.msg_rate:.0f} msg/s  |  TX: {s.tx_count}  |  错误: {s.error_count}")
        self.root.after(500, self._refresh)

    def _clear(self) -> None: self._tbl.clear(); self._log.clear()
    def _about(self) -> None:
        L_ = L()
        dlg = tk.Toplevel(self.root)
        dlg.title(L_["menu_about"])
        dlg.resizable(False, False)
        dlg.configure(bg=CARD)
        dlg.transient(self.root)
        dlg.grab_set()

        app_cfg = self.settings.get("app", {})
        version = app_cfg.get("version", "0.3.0")
        repo = app_cfg.get("repo", "https://github.com/xiyu1007/open-canoe")

        pad = 24
        tk.Label(dlg, text=f"open-canoe  v{version}",
                 font=(FONT_UI, 16, "bold"), bg=CARD, fg=PRIMARY).pack(
            padx=pad, pady=(pad, 6))
        tk.Label(dlg, text="Open CAN Bus Analyzer",
                 font=(FONT_UI, 10), bg=CARD, fg=SECONDARY).pack(pady=(0, 12))

        link_lbl = tk.Label(dlg, text=repo,
                            font=(FONT_UI, 9, "underline"), bg=CARD,
                            fg=ACCENT, cursor="hand2")
        link_lbl.pack(pady=(0, 12))
        link_lbl.bind("<Button-1>", lambda e: os.startfile(repo))

        desc = ("STM32 硬件探针 + 原生桌面 GUI\n"
                "USART 二进制协议通信 · 实时 CAN 报文追踪\n"
                "环回自测 · 周期发送 · 报文过滤 · 历史记录")
        tk.Label(dlg, text=desc, font=FONT_BODY, bg=CARD, fg=SECONDARY,
                 justify="center").pack(padx=pad, pady=(0, 16))

        btn_frame = tk.Frame(dlg, bg=CARD)
        btn_frame.pack(padx=pad, pady=(0, pad))
        ttk.Button(btn_frame, text="☕ " + L_.get("buy_coffee", "请我喝咖啡"),
                   command=self._show_sponsor).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text=L_.get("close", "关闭"),
                   command=dlg.destroy).pack(side=tk.LEFT)

        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = (dlg.winfo_screenwidth() - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"+{x}+{y}")

    def _show_sponsor(self) -> None:
        _app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sponsor_dir = os.path.join(_app_dir, "attachment")
        images = []
        for fname in ["Sponsor-Me.png", "Sponsor-MeAliPay.png"]:
            path = os.path.join(sponsor_dir, fname)
            if os.path.exists(path):
                try:
                    img = tk.PhotoImage(file=path)
                    w, h = img.width(), img.height()
                    scale = max(w, h) / 250
                    if scale > 1:
                        img = img.subsample(int(scale), int(scale))
                    images.append((img, fname))
                except Exception:
                    pass

        if not images:
            messagebox.showinfo("提示", "收款码图片未找到。", parent=self.root)
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("☕ 请我喝咖啡")
        dlg.resizable(False, False)
        dlg.configure(bg=CARD)
        dlg.transient(self.root)
        dlg.grab_set()

        pad, gap = 16, 12
        tk.Label(dlg, text="扫一扫，请我喝杯咖啡",
                 font=(FONT_UI, 13, "bold"), bg=CARD, fg=PRIMARY).pack(pady=(pad, 4))
        tk.Label(dlg, text="感谢支持！",
                 font=FONT_BODY, bg=CARD, fg=SECONDARY).pack(pady=(0, pad))

        img_frame = tk.Frame(dlg, bg=CARD)
        img_frame.pack(padx=pad)
        for img, name in images:
            card = tk.Frame(img_frame, bg="#f8fafc")
            card.pack(side=tk.LEFT, padx=gap // 2)
            lbl = tk.Label(card, image=img, bg="#f8fafc")
            lbl.image = img
            lbl.pack(padx=12, pady=12)
            label_text = "微信" if "WeChat" in name or "Sponsor-Me" == name.replace(".png","") else "支付宝"
            if "AliPay" in name:
                label_text = "支付宝"
            tk.Label(card, text=label_text, font=FONT_HINT,
                     bg="#f8fafc", fg=SECONDARY).pack(pady=(0, 8))

        ttk.Button(dlg, text="关闭", command=dlg.destroy).pack(pady=(pad, pad))

        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = (dlg.winfo_screenwidth() - w) // 2
        y = (dlg.winfo_screenheight() - h) // 2
        dlg.geometry(f"+{x}+{y}")

    def _center(self) -> None:
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _on_close(self) -> None:
        self._snd.stop_cycle()
        self._tbl.save_history_snapshot()
        self._disconnect()
        self.root.destroy()

    def run(self) -> None:
        self._refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
