"""CAN message send panel with single-shot, cyclic, and preset management."""
import json
import os
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLineEdit,
    QPushButton, QSpinBox, QComboBox, QLabel, QListWidget, QListWidgetItem,
    QMessageBox,
)
from ..i18n.manager import I18nManager
from ..protocol.protocol_defs import CANMode

PRESETS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "can_presets.json")


class CANSendPanel(QWidget):
    """Panel for sending CAN frames."""

    send_frame_requested = Signal(int, int, bytes, bool, bool, int)  # id, dlc, data, ide, rtr, channel
    mode_change_requested = Signal(int, int)  # mode, channel
    loopback_toggle_requested = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cyclic_timer = QTimer()
        self._cyclic_timer.timeout.connect(self._send_cyclic)
        self._cyclic_count = 0
        self._cyclic_current = 0
        self._presets: list[dict] = []
        self._load_presets()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # ID + Type row
        row1 = QHBoxLayout()
        row1.addWidget(QLabel(I18nManager.get("send.can_id")))
        self._id_edit = QLineEdit("0x123")
        self._id_edit.setMaximumWidth(120)
        row1.addWidget(self._id_edit)
        row1.addWidget(QLabel(I18nManager.get("send.type")))
        self._type_combo = QComboBox()
        self._type_combo.addItems([
            I18nManager.get("send.type_std"),
            I18nManager.get("send.type_ext"),
        ])
        row1.addWidget(self._type_combo)
        row1.addWidget(QLabel(I18nManager.get("send.channel")))
        self._channel_spin = QSpinBox()
        self._channel_spin.setRange(0, 1)
        self._channel_spin.setMaximumWidth(50)
        row1.addWidget(self._channel_spin)
        row1.addStretch()
        layout.addLayout(row1)

        # DLC + Data row
        row2 = QHBoxLayout()
        row2.addWidget(QLabel(I18nManager.get("send.dlc")))
        self._dlc_spin = QSpinBox()
        self._dlc_spin.setRange(0, 8)
        self._dlc_spin.setValue(8)
        self._dlc_spin.setMaximumWidth(60)
        row2.addWidget(self._dlc_spin)
        row2.addWidget(QLabel(I18nManager.get("send.data")))
        self._data_edit = QLineEdit("00 11 22 33 44 55 66 77")
        row2.addWidget(self._data_edit)
        layout.addLayout(row2)

        # Cyclic controls
        row3 = QHBoxLayout()
        row3.addWidget(QLabel(I18nManager.get("send.interval_ms")))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 10000)
        self._interval_spin.setValue(100)
        self._interval_spin.setSuffix(" ms")
        row3.addWidget(self._interval_spin)
        row3.addWidget(QLabel(I18nManager.get("send.count")))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 999999)
        self._count_spin.setValue(100)
        row3.addWidget(self._count_spin)
        self._infinite_cb = QPushButton(I18nManager.get("send.infinite"))
        self._infinite_cb.setCheckable(True)
        row3.addWidget(self._infinite_cb)
        layout.addLayout(row3)

        # Action buttons
        row4 = QHBoxLayout()
        send_btn = QPushButton(I18nManager.get("send.send_once"))
        send_btn.setObjectName("primaryBtn")
        send_btn.clicked.connect(self._send_once)
        row4.addWidget(send_btn)

        self._cyclic_btn = QPushButton(I18nManager.get("send.start_cyclic"))
        self._cyclic_btn.clicked.connect(self._toggle_cyclic)
        row4.addWidget(self._cyclic_btn)

        row4.addStretch()
        layout.addLayout(row4)

        # Mode control
        mode_group = QGroupBox("CAN Mode")
        mode_layout = QHBoxLayout(mode_group)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Normal", "Listen Only", "Loopback", "Loopback+Silent"])
        self._mode_combo.currentIndexChanged.connect(
            lambda i: self.mode_change_requested.emit(i, self._channel_spin.value()))
        mode_layout.addWidget(self._mode_combo)
        apply_mode_btn = QPushButton("Set")
        apply_mode_btn.clicked.connect(
            lambda: self.mode_change_requested.emit(
                self._mode_combo.currentIndex(), self._channel_spin.value()))
        mode_layout.addWidget(apply_mode_btn)
        layout.addWidget(mode_group)

        # Presets
        preset_group = QGroupBox(I18nManager.get("send.presets"))
        preset_layout = QVBoxLayout(preset_group)
        preset_row = QHBoxLayout()
        save_btn = QPushButton(I18nManager.get("send.save_preset"))
        save_btn.clicked.connect(self._save_preset)
        preset_row.addWidget(save_btn)
        load_btn = QPushButton(I18nManager.get("send.load_preset"))
        load_btn.clicked.connect(self._load_selected_preset)
        preset_row.addWidget(load_btn)
        del_btn = QPushButton(I18nManager.get("send.delete_preset"))
        del_btn.clicked.connect(self._delete_preset)
        preset_row.addWidget(del_btn)
        preset_layout.addLayout(preset_row)
        self._preset_list = QListWidget()
        self._preset_list.setMaximumHeight(100)
        self._refresh_preset_list()
        preset_layout.addWidget(self._preset_list)
        layout.addWidget(preset_group)

    # ---- Parsing ----

    def _parse_id(self) -> int:
        text = self._id_edit.text().strip()
        if text.startswith("0x") or text.startswith("0X"):
            return int(text, 16)
        return int(text, 16) if all(c in "0123456789ABCDEFabcdef" for c in text) else int(text, 0)

    def _parse_data(self) -> bytes:
        text = self._data_edit.text().strip()
        parts = text.replace(",", " ").split()
        return bytes([int(p, 16) for p in parts[:8]])

    # ---- Send ----

    def _send_once(self):
        try:
            can_id = self._parse_id()
            dlc = self._dlc_spin.value()
            data = self._parse_data()
            ide = self._type_combo.currentIndex() == 1
            channel = self._channel_spin.value()
        except (ValueError, IndexError):
            QMessageBox.warning(self, I18nManager.get("dialog.error"), "Invalid CAN ID or data format")
            return
        self.send_frame_requested.emit(can_id, dlc, data, ide, False, channel)

    def _toggle_cyclic(self):
        if self._cyclic_timer.isActive():
            self._cyclic_timer.stop()
            self._cyclic_btn.setText(I18nManager.get("send.start_cyclic"))
            return
        try:
            self._parse_id()
            self._parse_data()
        except (ValueError, IndexError):
            QMessageBox.warning(self, I18nManager.get("dialog.error"), "Invalid CAN ID or data format")
            return
        self._cyclic_count = self._count_spin.value()
        self._cyclic_current = 0
        self._cyclic_timer.start(self._interval_spin.value())
        self._cyclic_btn.setText(I18nManager.get("send.stop_cyclic"))

    def _send_cyclic(self):
        if not self._infinite_cb.isChecked():
            self._cyclic_current += 1
            if self._cyclic_current > self._cyclic_count:
                self._cyclic_timer.stop()
                self._cyclic_btn.setText(I18nManager.get("send.start_cyclic"))
                return
        self._send_once()

    # ---- Presets ----

    def _load_presets(self):
        try:
            if os.path.exists(PRESETS_FILE):
                with open(PRESETS_FILE, 'r', encoding='utf-8') as f:
                    self._presets = json.load(f)
        except Exception:
            self._presets = []

    def _save_presets(self):
        try:
            os.makedirs(os.path.dirname(PRESETS_FILE), exist_ok=True)
            with open(PRESETS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self._presets, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _refresh_preset_list(self):
        self._preset_list.clear()
        for p in self._presets:
            item = QListWidgetItem(p.get("name", "Unnamed"))
            item.setData(Qt.UserRole, p)
            self._preset_list.addItem(item)

    def _save_preset(self):
        name = f"ID={self._id_edit.text()} DLC={self._dlc_spin.value()}"
        preset = {
            "name": name,
            "can_id": self._id_edit.text(),
            "dlc": self._dlc_spin.value(),
            "data": self._data_edit.text(),
            "type": self._type_combo.currentIndex(),
            "interval": self._interval_spin.value(),
            "count": self._count_spin.value(),
        }
        self._presets.append(preset)
        self._save_presets()
        self._refresh_preset_list()

    def _load_selected_preset(self):
        item = self._preset_list.currentItem()
        if not item:
            return
        p = item.data(Qt.UserRole)
        self._id_edit.setText(p.get("can_id", "0x123"))
        self._dlc_spin.setValue(p.get("dlc", 8))
        self._data_edit.setText(p.get("data", ""))
        self._type_combo.setCurrentIndex(p.get("type", 0))
        self._interval_spin.setValue(p.get("interval", 100))
        self._count_spin.setValue(p.get("count", 100))

    def _delete_preset(self):
        row = self._preset_list.currentRow()
        if row >= 0:
            del self._presets[row]
            self._save_presets()
            self._refresh_preset_list()
