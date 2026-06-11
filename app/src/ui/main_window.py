"""Main application window for Open-Canoe."""
import os
import sys
import json
from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtWidgets import (
    QMainWindow, QMenuBar, QMenu, QToolBar, QStatusBar,
    QDockWidget, QMessageBox, QLabel, QWidget, QVBoxLayout,
    QApplication, QFileDialog,
)
from PySide6.QtGui import QAction, QActionGroup, QIcon

from ..i18n.manager import I18nManager
from ..protocol.protocol_defs import Command, CANMode
from ..protocol.command_builder import CommandBuilder
from ..device.device_manager import DeviceManager, MockDeviceManager
from ..device.mock_hardware import MockHardware
from ..device.serial_scanner import scan_ports, find_any_serial
from .can_table import CANTableView
from .can_send_panel import CANSendPanel
from .stats_panel import StatsPanel
from .device_panel import DevicePanel
from .waveform_window import WaveformWindow
from .flash_dialog import FlashDialog
from .settings_dialog import SettingsDialog
from .styles import get_theme_stylesheet


class MainWindow(QMainWindow):
    """Open-Canoe main application window."""

    def __init__(self, mock_mode: bool = False):
        super().__init__()
        self._mock_mode = mock_mode
        self._dark_theme = True
        self._current_lang = "en"
        self._test_results: list[tuple[str, bool]] = []

        # Device manager
        if mock_mode:
            self._mock_hw = MockHardware("STM32F407VET6")
            self._device = MockDeviceManager(self._mock_hw)
        else:
            self._mock_hw = None
            self._device = DeviceManager()

        # Window state
        self._waveform_window: WaveformWindow | None = None
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start(2000)

        # Setup UI
        self._setup_window()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_central()
        self._setup_docks()
        self._setup_statusbar()
        self._connect_signals()

        # Apply theme
        self._apply_theme()

        # Auto-connect in mock mode
        if mock_mode:
            self._device.connect("MOCK")
            self._on_connected()

    # ---- Window ----

    def _setup_window(self):
        self.setWindowTitle(I18nManager.get("app.title"))
        self.resize(1400, 900)
        self.setMinimumSize(1024, 600)

    # ---- Menu ----

    def _setup_menu(self):
        mb = self.menuBar()

        # File
        file_menu = mb.addMenu(I18nManager.get("menu.file"))
        self._connect_action = file_menu.addAction(I18nManager.get("menu.file.connect"))
        self._connect_action.triggered.connect(self._do_connect)
        self._disconnect_action = file_menu.addAction(I18nManager.get("menu.file.disconnect"))
        self._disconnect_action.triggered.connect(self._do_disconnect)
        self._disconnect_action.setEnabled(False)
        file_menu.addSeparator()
        file_menu.addAction(I18nManager.get("menu.file.exit"), self.close)

        # View
        view_menu = mb.addMenu(I18nManager.get("menu.view"))
        self._view_send_action = view_menu.addAction(I18nManager.get("menu.view.send_panel"))
        self._view_send_action.setCheckable(True)
        self._view_send_action.setChecked(True)
        self._view_stats_action = view_menu.addAction(I18nManager.get("menu.view.stats_panel"))
        self._view_stats_action.setCheckable(True)
        self._view_stats_action.setChecked(True)
        self._view_device_action = view_menu.addAction(I18nManager.get("menu.view.device_panel"))
        self._view_device_action.setCheckable(True)
        self._view_device_action.setChecked(True)
        view_menu.addSeparator()
        waveform_action = view_menu.addAction(I18nManager.get("menu.view.waveform"))
        waveform_action.triggered.connect(self._toggle_waveform)

        # Settings
        settings_menu = mb.addMenu(I18nManager.get("menu.settings"))
        settings_menu.addAction(I18nManager.get("menu.settings.params"), self._open_settings)

        # Language submenu
        lang_menu = settings_menu.addMenu(I18nManager.get("menu.settings.language"))
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        lang_en = lang_menu.addAction("English")
        lang_en.setCheckable(True)
        lang_en.setChecked(True)
        lang_en.triggered.connect(lambda: self._switch_language("en"))
        lang_zh = lang_menu.addAction("中文")
        lang_zh.setCheckable(True)
        lang_zh.triggered.connect(lambda: self._switch_language("zh"))
        self._lang_group.addAction(lang_en)
        self._lang_group.addAction(lang_zh)

        # Theme submenu
        theme_menu = settings_menu.addMenu(I18nManager.get("menu.settings.theme"))
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        theme_dark = theme_menu.addAction(I18nManager.get("menu.settings.theme_dark"))
        theme_dark.setCheckable(True)
        theme_dark.setChecked(True)
        theme_dark.triggered.connect(lambda: self._switch_theme(True))
        theme_light = theme_menu.addAction(I18nManager.get("menu.settings.theme_light"))
        theme_light.setCheckable(True)
        theme_light.triggered.connect(lambda: self._switch_theme(False))
        self._theme_group.addAction(theme_dark)
        self._theme_group.addAction(theme_light)

        # Help
        help_menu = mb.addMenu(I18nManager.get("menu.help"))
        help_menu.addAction(I18nManager.get("menu.help.about"), self._show_about)

    # ---- Toolbar ----

    def _setup_toolbar(self):
        self._toolbar = QToolBar("Main")
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)

        self._tb_connect = self._toolbar.addAction(I18nManager.get("app.toolbar.connect"))
        self._tb_connect.triggered.connect(self._do_connect)
        self._tb_disconnect = self._toolbar.addAction(I18nManager.get("app.toolbar.disconnect"))
        self._tb_disconnect.triggered.connect(self._do_disconnect)
        self._tb_disconnect.setEnabled(False)

        self._toolbar.addSeparator()

        self._tb_start_can = self._toolbar.addAction(I18nManager.get("app.toolbar.start_can"))
        self._tb_start_can.triggered.connect(self._start_can)
        self._tb_start_can.setEnabled(False)
        self._tb_stop_can = self._toolbar.addAction(I18nManager.get("app.toolbar.stop_can"))
        self._tb_stop_can.triggered.connect(self._stop_can)
        self._tb_stop_can.setEnabled(False)

        self._toolbar.addSeparator()

        self._tb_start_adc = self._toolbar.addAction(I18nManager.get("app.toolbar.start_adc"))
        self._tb_start_adc.triggered.connect(self._start_adc)
        self._tb_start_adc.setEnabled(False)
        self._tb_stop_adc = self._toolbar.addAction(I18nManager.get("app.toolbar.stop_adc"))
        self._tb_stop_adc.triggered.connect(self._stop_adc)
        self._tb_stop_adc.setEnabled(False)

        self._toolbar.addSeparator()

        self._tb_loopback = self._toolbar.addAction(I18nManager.get("app.toolbar.loopback"))
        self._tb_loopback.setCheckable(True)
        self._tb_loopback.triggered.connect(self._toggle_loopback)
        self._tb_loopback.setEnabled(False)

        self._tb_flash = self._toolbar.addAction(I18nManager.get("app.toolbar.flash"))
        self._tb_flash.triggered.connect(self._open_flash_dialog)

    # ---- Central Widget ----

    def _setup_central(self):
        self._can_table = CANTableView()
        self.setCentralWidget(self._can_table)

    # ---- Docks ----

    def _setup_docks(self):
        # Send panel dock (bottom)
        self._send_panel = CANSendPanel()
        self._send_dock = QDockWidget(I18nManager.get("send.title"))
        self._send_dock.setWidget(self._send_panel)
        self._send_dock.setObjectName("SendPanel")
        self.addDockWidget(Qt.BottomDockWidgetArea, self._send_dock)

        # Stats panel dock (right)
        self._stats_panel = StatsPanel()
        self._stats_dock = QDockWidget(I18nManager.get("stats.title"))
        self._stats_dock.setWidget(self._stats_panel)
        self._stats_dock.setObjectName("StatsPanel")
        self.addDockWidget(Qt.RightDockWidgetArea, self._stats_dock)

        # Device panel dock (right)
        self._device_panel = DevicePanel()
        self._device_dock = QDockWidget(I18nManager.get("device.title"))
        self._device_dock.setWidget(self._device_panel)
        self._device_dock.setObjectName("DevicePanel")
        self.addDockWidget(Qt.RightDockWidgetArea, self._device_dock)

        # Tabify stats and device docks
        self.tabifyDockWidget(self._stats_dock, self._device_dock)
        self._stats_dock.raise_()

        # Connect view menu toggles
        self._view_send_action.toggled.connect(lambda v: self._send_dock.setVisible(v))
        self._view_stats_action.toggled.connect(lambda v: self._stats_dock.setVisible(v))
        self._view_device_action.toggled.connect(lambda v: self._device_dock.setVisible(v))

    # ---- Status Bar ----

    def _setup_statusbar(self):
        sb = self.statusBar()
        self._sb_conn = QLabel(I18nManager.get("status.disconnected"))
        self._sb_conn.setStyleSheet("color: #f38ba8;")
        sb.addWidget(self._sb_conn)
        sb.addWidget(QLabel("  |  "))
        self._sb_mcu = QLabel(f"{I18nManager.get('status.mcu')}: -")
        sb.addWidget(self._sb_mcu)
        sb.addWidget(QLabel("  |  "))
        self._sb_fw = QLabel(f"{I18nManager.get('status.fw')}: -")
        sb.addWidget(self._sb_fw)
        sb.addWidget(QLabel("  |  "))
        self._sb_port = QLabel(f"{I18nManager.get('status.port')}: -")
        sb.addWidget(self._sb_port)
        sb.addWidget(QLabel("  |  "))
        self._sb_tx = QLabel(f"{I18nManager.get('status.tx')}: 0")
        sb.addWidget(self._sb_tx)
        sb.addWidget(QLabel("  |  "))
        self._sb_rx = QLabel(f"{I18nManager.get('status.rx')}: 0")
        sb.addWidget(self._sb_rx)
        sb.addWidget(QLabel("  |  "))
        self._sb_err = QLabel(f"{I18nManager.get('status.err')}: 0")
        sb.addWidget(self._sb_err)

    # ---- Signals ----

    def _connect_signals(self):
        # Device callbacks
        self._device.set_general_callback(self._on_frame_received)

        # Send panel
        self._send_panel.send_frame_requested.connect(self._on_send_frame)
        self._send_panel.mode_change_requested.connect(self._on_set_mode)

    # ---- Connection ----

    def _do_connect(self):
        if self._device.is_connected:
            return
        if self._mock_mode:
            self._device.connect("MOCK")
            self._on_connected()
            return
        # Try last port or auto-scan
        port = None
        settings_path = os.path.join(os.path.dirname(__file__), "..", "..", "settings.json")
        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    s = json.load(f)
                    port = s.get("port", "")
        except Exception:
            pass
        if not port:
            port = find_any_serial()
        if not port:
            QMessageBox.warning(self, I18nManager.get("dialog.warning"),
                                I18nManager.get("log.no_ports"))
            return
        ok = self._device.connect(port, 115200)
        if ok:
            self._on_connected()
        else:
            self._log(f"Failed to connect to {port}")

    def _do_disconnect(self):
        self._device.disconnect()
        self._on_disconnected()

    def _on_connected(self):
        self._sb_conn.setText(I18nManager.get("status.connected"))
        self._sb_conn.setStyleSheet("color: #a6e3a1;")
        self._sb_port.setText(f"{I18nManager.get('status.port')}: {self._device.port}")
        self._connect_action.setEnabled(False)
        self._disconnect_action.setEnabled(True)
        self._tb_connect.setEnabled(False)
        self._tb_disconnect.setEnabled(True)
        self._tb_start_can.setEnabled(True)
        self._tb_stop_can.setEnabled(True)
        self._tb_start_adc.setEnabled(True)
        self._tb_stop_adc.setEnabled(True)
        self._tb_loopback.setEnabled(True)
        # Query device
        QTimer.singleShot(200, self._query_device)

    def _on_disconnected(self):
        self._sb_conn.setText(I18nManager.get("status.disconnected"))
        self._sb_conn.setStyleSheet("color: #f38ba8;")
        self._sb_mcu.setText(f"{I18nManager.get('status.mcu')}: -")
        self._sb_port.setText(f"{I18nManager.get('status.port')}: -")
        self._connect_action.setEnabled(True)
        self._disconnect_action.setEnabled(False)
        self._tb_connect.setEnabled(True)
        self._tb_disconnect.setEnabled(False)
        self._tb_start_can.setEnabled(False)
        self._tb_stop_can.setEnabled(False)
        self._tb_start_adc.setEnabled(False)
        self._tb_stop_adc.setEnabled(False)
        self._tb_loopback.setEnabled(False)
        self._device_panel.clear()

    def _query_device(self):
        self._device.query_info()
        QTimer.singleShot(100, self._device.query_capabilities)

    # ---- Frame Dispatch ----

    def _on_frame_received(self, cmd: int, seq: int, data: bytes):
        if cmd == Command.INFO_RESPONSE:
            info = CommandBuilder.parse_device_info(data)
            self._device.device_info = info
            self._device.mcu_model = info.get("mcu_model", "Unknown")
            self._device.fw_version = info.get("fw_version", "?")
            self._sb_mcu.setText(f"{I18nManager.get('status.mcu')}: {self._device.mcu_model}")
            self._sb_fw.setText(f"{I18nManager.get('status.fw')}: {self._device.fw_version}")
            self._device_panel.update_device_info(info)
            self._log(f"Device identified: {self._device.mcu_model} (FW {self._device.fw_version})")

        elif cmd == Command.CAPABILITIES_RESPONSE:
            caps = CommandBuilder.parse_capabilities(data)
            self._device.capabilities = caps
            self._device_panel.update_capabilities(caps)
            if not caps.get("has_adc"):
                self._tb_start_adc.setEnabled(False)
                self._tb_stop_adc.setEnabled(False)

        elif cmd == Command.STATUS_RESPONSE:
            status = CommandBuilder.parse_status(data)
            self._device.status = status
            self._device_panel.update_interface(status.get("comm_interface", "-"))
            self._tb_loopback.setChecked(status.get("can_loopback", False))

        elif cmd == Command.CAN_FRAME_UP:
            frame = CommandBuilder.parse_can_frame(data)
            self._can_table.add_message(frame)
            self._stats_panel.add_rx()
            self._sb_rx.setText(f"{I18nManager.get('status.rx')}: {self._can_table.row_count()}")
            if frame.get("is_error"):
                self._stats_panel.add_error()
                self._sb_err.setText(f"{I18nManager.get('status.err')}: {self._stats_panel._error_count}")  # noqa

        elif cmd == Command.ADC_DATA_UP:
            adc_data = CommandBuilder.parse_adc_data(data)
            if self._waveform_window and self._waveform_window.isVisible():
                self._waveform_window.add_adc_packet(adc_data)

        elif cmd == Command.ERROR_NOTIFY:
            err = CommandBuilder.parse_error(data)

        elif cmd == Command.DEVICE_HEARTBEAT:
            hb = CommandBuilder.parse_heartbeat(data)
            self._sb_mcu.setText(f"{I18nManager.get('status.mcu')}: {hb.get('mcu_model', '?')}")
            self._device.mcu_model = hb.get("mcu_model", "Unknown")
            self._device.fw_version = hb.get("fw_version", "?")

        elif cmd == Command.ACK:
            ack = CommandBuilder.parse_ack(data)
            cmd_name = {0x30: "CAN_START", 0x31: "CAN_STOP", 0x32: "ADC_START",
                        0x33: "ADC_STOP", 0x34: "CAN_SEND", 0x11: "CAN_MODE"}.get(ack.get("ack_cmd", 0), f"0x{ack['ack_cmd']:02X}")
            if not ack["is_ok"]:
                pass  # Silent NACK logging

    # ---- CAN Control ----

    def _start_can(self):
        self._device.start_can_listen()

    def _stop_can(self):
        self._device.stop_can_listen()

    def _toggle_loopback(self, checked: bool):
        mode = CANMode.LOOPBACK if checked else CANMode.NORMAL
        self._device.set_can_mode(mode)

    def _on_set_mode(self, mode: int, channel: int):
        self._device.set_can_mode(mode, channel)

    def _on_send_frame(self, can_id: int, dlc: int, data: bytes,
                       ide: bool, rtr: bool, channel: int):
        self._device.send_can_frame(can_id, dlc, data, ide=ide, rtr=rtr, channel=channel)
        self._stats_panel.add_tx()
        self._sb_tx.setText(f"{I18nManager.get('status.tx')}: {self._stats_panel._tx_count}")

    # ---- ADC Control ----

    def _start_adc(self):
        self._device.start_adc()
        if self._waveform_window:
            self._waveform_window.show()

    def _stop_adc(self):
        self._device.stop_adc()

    # ---- Waveform ----

    def _toggle_waveform(self):
        if self._waveform_window is None:
            self._waveform_window = WaveformWindow(self)
        if self._waveform_window.isVisible():
            self._waveform_window.hide()
        else:
            self._waveform_window.show()

    # ---- Flash ----

    def _open_flash_dialog(self):
        dlg = FlashDialog(self)
        dlg.exec()

    # ---- Settings ----

    def _open_settings(self):
        dlg = SettingsDialog(self)
        if dlg.exec():
            pass  # Settings applied

    # ---- Theme ----

    def _switch_theme(self, dark: bool):
        self._dark_theme = dark
        self._apply_theme()

    def _apply_theme(self):
        app = QApplication.instance()
        app.setStyleSheet(get_theme_stylesheet(self._dark_theme))
        self._can_table.model().set_dark_theme(self._dark_theme)

    # ---- Language ----

    def _switch_language(self, lang: str):
        self._current_lang = lang
        I18nManager.set_language(lang)
        self._retranslate()

    def _retranslate(self):
        self.setWindowTitle(I18nManager.get("app.title"))
        # This is a simplified refresh — a full app would rebuild menus, etc.

    # ---- Poll ----

    def _poll_status(self):
        if self._device.is_connected:
            self._device.query_status()

    # ---- Helpers ----

    def _show_about(self):
        QMessageBox.about(self, "Open-Canoe", I18nManager.get("dialog.about_text"))

    def _log(self, msg: str):
        print(f"[Open-Canoe] {msg}")

    # ---- Test Support ----

    def run_test(self, test_name: str, test_fn) -> bool:
        """Run a test function and record result."""
        try:
            test_fn()
            result = True
            self._log(I18nManager.get("log.test_pass", test_name=test_name))
        except Exception as e:
            result = False
            self._log(I18nManager.get("log.test_fail", test_name=test_name))
            self._log(f"  Reason: {e}")
        self._test_results.append((test_name, result))
        return result

    def get_test_results(self) -> list[tuple[str, bool]]:
        return list(self._test_results)
