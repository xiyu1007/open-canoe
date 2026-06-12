"""open-canoe 主窗口 — 简洁布局，可折叠面板自动重排。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
import threading, queue, time

from canoe.config.settings import load_settings
from canoe.core.models import CANMessage
from canoe.core.transport import auto_detect, TransportError, list_serial_ports
from canoe.core.protocol import encode, Command

from canoe.gui.config import *
from canoe.gui.lang import L, set_lang, lang_code
from canoe.gui.message_table import MessageTable
from canoe.gui.device_bar import DeviceBar
from canoe.gui.send_panel import SendPanel
from canoe.gui.detail_panel import DetailPanel
from canoe.gui.log_panel import LogPanel
from canoe.gui.waveform_window import WaveformWindow


class MainWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.settings = load_settings()
        self._tr = None
        self._wave = None
        self._q: queue.Queue = queue.Queue()

        self._v_detail = tk.BooleanVar(value=True)
        self._v_log    = tk.BooleanVar(value=True)
        self._v_left   = tk.BooleanVar(value=True)
        self._v_right  = tk.BooleanVar(value=True)

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
        s.configure("Treeview", font=FONT_BODY, rowheight=22)
        s.configure("Treeview.Heading", font=FONT_SECTION)

    def _build_layout(self) -> None:
        L_ = L()
        outer = ttk.Frame(self.root, padding=(12, 10))
        outer.pack(fill=tk.BOTH, expand=True)

        tf = ttk.Frame(outer)
        tf.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(tf, text=L_["title"], style="Title.TLabel").pack(side=tk.LEFT)

        self._main = ttk.Frame(outer)
        self._main.pack(fill=tk.BOTH, expand=True)
        self._main.columnconfigure(1, weight=1)
        self._main.rowconfigure(0, weight=1)

        # 左栏
        self._frame_left = ttk.Frame(self._main)
        self._card_left = ttk.Frame(self._frame_left, style="Card.TFrame", padding=14)
        self._card_left.pack(fill=tk.BOTH, expand=True)
        self._dev = DeviceBar(
            self._card_left,
            on_connect=self._connect_async,
            on_disconnect=self._disconnect,
            on_waveform=self._open_waveform,
            on_flash=self._flash_dialog,
        )
        self._dev.pack(fill=tk.BOTH, expand=True)

        # 中栏
        self._frame_ctr = ttk.Frame(self._main)
        self._frame_ctr.rowconfigure(0, weight=1)

        self._card_trace = ttk.Frame(self._frame_ctr, style="Card.TFrame", padding=14)
        self._card_trace.rowconfigure(0, weight=1); self._card_trace.columnconfigure(0, weight=1)
        self._tbl = MessageTable(self._card_trace, max_rows=self.settings.ui.max_log_lines)
        self._tbl.pack(fill=tk.BOTH, expand=True)

        self._frame_det = ttk.Frame(self._frame_ctr)
        self._card_det = ttk.Frame(self._frame_det, style="Card.TFrame", padding=14)
        self._card_det.pack(fill=tk.BOTH, expand=True)
        self._det = DetailPanel(self._card_det)
        self._det.pack(fill=tk.BOTH, expand=True)

        # 右栏
        self._frame_right = ttk.Frame(self._main)
        self._card_right = ttk.Frame(self._frame_right, style="Card.TFrame", padding=14)
        self._card_right.pack(fill=tk.BOTH, expand=True)
        self._snd = SendPanel(self._card_right, on_send=self._on_send, on_filter=self._on_filter)
        self._snd.pack(fill=tk.BOTH, expand=True)

        # 日志
        self._frame_log = ttk.Frame(outer)
        self._card_log = ttk.Frame(self._frame_log, style="Card.TFrame", padding=14)
        self._card_log.pack(fill=tk.X)
        self._log = LogPanel(self._card_log)
        self._log.pack(fill=tk.X)

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
        for w in (self._frame_left, self._frame_ctr, self._frame_right):
            w.grid_forget()

        if self._v_left.get():
            self._frame_left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._frame_ctr.grid(row=0, column=1, sticky="nsew")
        if self._v_right.get():
            self._frame_right.grid(row=0, column=2, sticky="ns", padx=(6, 0))

        if self._v_detail.get():
            self._card_trace.pack(fill=tk.BOTH, expand=True, pady=(0, 4))
            self._frame_det.pack(fill=tk.X, pady=(4, 0))
        else:
            self._card_trace.pack(fill=tk.BOTH, expand=True)
            self._frame_det.pack_forget()

        if self._v_log.get():
            self._frame_log.pack(fill=tk.X, pady=(8, 0))
        else:
            self._frame_log.pack_forget()

    def _build_menu(self) -> None:
        L_ = L()
        mb = tk.Menu(self.root, font=FONT_BODY)
        self.root.config(menu=mb)
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
        mb.add_cascade(label=L_["menu_view"], menu=vm)
        sm = tk.Menu(mb, tearoff=0)
        lm = tk.Menu(sm, tearoff=0)
        lm.add_radiobutton(label="中文", command=lambda: self._switch_lang("ZH"))
        lm.add_radiobutton(label="English", command=lambda: self._switch_lang("EN"))
        sm.add_cascade(label=L_["menu_lang"], menu=lm)
        mb.add_cascade(label=L_["menu_settings"], menu=sm)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label=L_["menu_about"], command=self._about)
        mb.add_cascade(label=L_["menu_help"], menu=hm)

    def _switch_lang(self, code: str) -> None:
        set_lang(code)
        messagebox.showinfo(L()["menu_lang"],
            "请重启程序使语言设置生效。\nRestart to apply language change.")

    def _connect_async(self) -> None:
        if self._tr is not None: self._disconnect(); return
        port = self._dev.selected_port
        self._dev.set_connecting()
        self._status_var.set(L()["connecting"])
        threading.Thread(target=self._conn_thread, args=(port,), daemon=True).start()

    def _conn_thread(self, port: str) -> None:
        try:
            if port and port != "auto":
                from canoe.core.transport import SerialTransport
                tr = SerialTransport(port=port, baudrate=self.settings.transport.serial_baud)
            else:
                tr = auto_detect(baudrate=self.settings.transport.serial_baud)
            tr.connect()
            self._q.put(("ok", tr))
        except TransportError as e:
            self._q.put(("err", str(e)))
        except Exception as e:
            self._q.put(("err", str(e)))

    def _disconnect(self) -> None:
        if self._tr:
            try: self._tr.disconnect()
            except Exception: pass
            self._tr = None
        self._dev.set_disconnected()
        self._status_var.set(L()["disconnected"])

    def _poll(self) -> None:
        try:
            while True:
                kind, data = self._q.get_nowait()
                L_ = L()
                if kind == "ok":
                    self._tr = data
                    self._dev.set_connected(self._tr.info.port)
                    self._status_var.set(f"{L_['connected']} — {self._tr.info.port}")
                    self._log.log(f"Connected: {self._tr.info.port}", "ok")
                elif kind == "err":
                    messagebox.showwarning(L_["no_device"], data)
                    self._log.log(data, "err")
                    self._dev.set_disconnected()
                    self._status_var.set(L_["disconnected"])
        except queue.Empty:
            pass
        self.root.after(200, self._poll)

    def _on_filter(self, ids: set[int], mode: str) -> None:
        self._tbl.set_filter(ids, mode)

    def _on_send(self, msg: CANMessage) -> None:
        self._tbl.add(msg)
        if self._tr and self._tr.is_connected:
            try:
                self._tr.write(encode(Command.CAN_SEND, msg.data))
                self._tbl.stats.record_tx()
            except Exception as e:
                self._log.log(f"发送失败: {e}", "err")

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
            data = bytes.fromhex(vals[5].replace(" ", ""))
            self._det.show(CANMessage(
                arbitration_id=can_id, data=data, is_extended=is_ext, is_error=is_err))
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
        f = ttk.Frame(dlg, padding=16); f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text=L_["flash_select"], font=FONT_SECTION).pack(anchor=tk.W)
        mcu = tk.StringVar(value="STM32F103C8T6")
        ttk.Radiobutton(f, text=L_["flash_info_f103"],
                        variable=mcu, value="STM32F103C8T6").pack(anchor=tk.W, pady=(4, 8))
        ttk.Radiobutton(f, text=L_["flash_info_f407"],
                        variable=mcu, value="STM32F407VET6").pack(anchor=tk.W, pady=(0, 8))
        ttk.Separator(f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=4)
        txt = tk.Text(f, height=8, font=FONT_MONO_9, bg="#f8fafc", relief="flat", borderwidth=1)
        txt.pack(fill=tk.BOTH, expand=True, pady=(4, 8)); txt.insert("1.0", L_["flash_steps"])
        txt.config(state=tk.DISABLED)
        ttk.Button(f, text="OK", command=dlg.destroy).pack(side=tk.RIGHT)

    def _refresh(self) -> None:
        s = self._tbl.stats
        self._rate_var.set(f"RX: {s.msg_rate:.0f} msg/s  |  TX: {s.tx_count}  |  错误: {s.error_count}")
        self.root.after(500, self._refresh)

    def _clear(self) -> None: self._tbl.clear(); self._log.clear()
    def _about(self) -> None: messagebox.showinfo(L()["menu_about"], L()["about"])

    def _center(self) -> None:
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"+{x}+{y}")

    def _on_close(self) -> None:
        self._snd.stop_cycle(); self._disconnect(); self.root.destroy()

    def run(self) -> None:
        self._refresh()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()
