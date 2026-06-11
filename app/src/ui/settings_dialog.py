"""Settings dialog for communication, CAN, and ADC parameters."""
import json
import os
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QGroupBox, QLabel, QLineEdit, QSpinBox, QComboBox,
    QCheckBox, QPushButton, QFormLayout,
)
from ..i18n.manager import I18nManager
from ..device.serial_scanner import scan_ports

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "settings.json")


class SettingsDialog(QDialog):
    """Application settings dialog with tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(I18nManager.get("settings.title"))
        self.resize(450, 400)
        self._settings: dict = {}
        self._load_settings()
        self._setup_ui()
        self._apply_settings()

    def _load_settings(self):
        defaults = {
            "port": "", "baudrate": 115200, "auto_scan": True,
            "can_baudrate": 500000, "can_mode": 0,
            "adc_rate": 100000, "adc_resolution": 12,
        }
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
        self._settings = defaults

    def _save_settings(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self._settings, f, indent=2)
        except Exception:
            pass

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        tabs = QTabWidget()

        # Communication tab
        comm_tab = QWidget()
        comm_form = QFormLayout(comm_tab)

        port_layout = QHBoxLayout()
        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._refresh_ports()
        port_layout.addWidget(self._port_combo, 1)
        refresh_btn = QPushButton("↻")
        refresh_btn.setMaximumWidth(40)
        refresh_btn.clicked.connect(self._refresh_ports)
        port_layout.addWidget(refresh_btn)
        comm_form.addRow(I18nManager.get("settings.port"), port_layout)

        self._baudrate_combo = QComboBox()
        self._baudrate_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        self._baudrate_combo.setCurrentText("115200")
        comm_form.addRow(I18nManager.get("settings.baudrate"), self._baudrate_combo)

        self._auto_scan_cb = QCheckBox()
        self._auto_scan_cb.setChecked(self._settings.get("auto_scan", True))
        comm_form.addRow(I18nManager.get("settings.auto_scan"), self._auto_scan_cb)

        tabs.addTab(comm_tab, I18nManager.get("settings.comm"))

        # CAN tab
        can_tab = QWidget()
        can_form = QFormLayout(can_tab)
        self._can_baud_spin = QSpinBox()
        self._can_baud_spin.setRange(10000, 1000000)
        self._can_baud_spin.setSingleStep(50000)
        self._can_baud_spin.setValue(self._settings.get("can_baudrate", 500000))
        can_form.addRow(I18nManager.get("settings.can_baudrate"), self._can_baud_spin)

        self._can_mode_combo = QComboBox()
        self._can_mode_combo.addItems([
            I18nManager.get("settings.mode_normal"),
            I18nManager.get("settings.mode_listen"),
            I18nManager.get("settings.mode_loopback"),
        ])
        self._can_mode_combo.setCurrentIndex(self._settings.get("can_mode", 0))
        can_form.addRow(I18nManager.get("settings.can_mode"), self._can_mode_combo)

        tabs.addTab(can_tab, I18nManager.get("settings.can"))

        # ADC tab
        adc_tab = QWidget()
        adc_form = QFormLayout(adc_tab)
        self._adc_rate_spin = QSpinBox()
        self._adc_rate_spin.setRange(1000, 5000000)
        self._adc_rate_spin.setSingleStep(10000)
        self._adc_rate_spin.setValue(self._settings.get("adc_rate", 100000))
        adc_form.addRow(I18nManager.get("settings.adc_rate"), self._adc_rate_spin)

        self._adc_res_spin = QSpinBox()
        self._adc_res_spin.setRange(8, 12)
        self._adc_res_spin.setValue(self._settings.get("adc_resolution", 12))
        adc_form.addRow(I18nManager.get("settings.adc_resolution"), self._adc_res_spin)

        tabs.addTab(adc_tab, I18nManager.get("settings.adc"))

        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        apply_btn = QPushButton(I18nManager.get("settings.apply"))
        apply_btn.setObjectName("primaryBtn")
        apply_btn.clicked.connect(self._on_apply)
        btn_layout.addWidget(apply_btn)
        cancel_btn = QPushButton(I18nManager.get("settings.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _refresh_ports(self):
        self._port_combo.clear()
        ports = scan_ports()
        for p in ports:
            self._port_combo.addItem(f"{p['port']} - {p['description']}", p['port'])

    def _apply_settings(self):
        self._port_combo.setCurrentText(self._settings.get("port", ""))

    def _on_apply(self):
        self._settings["port"] = self._port_combo.currentText().split(" - ")[0]
        self._settings["baudrate"] = int(self._baudrate_combo.currentText())
        self._settings["auto_scan"] = self._auto_scan_cb.isChecked()
        self._settings["can_baudrate"] = self._can_baud_spin.value()
        self._settings["can_mode"] = self._can_mode_combo.currentIndex()
        self._settings["adc_rate"] = self._adc_rate_spin.value()
        self._settings["adc_resolution"] = self._adc_res_spin.value()
        self._save_settings()
        self.accept()

    def get_settings(self) -> dict:
        return dict(self._settings)
