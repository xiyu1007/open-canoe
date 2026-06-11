"""Device info and capabilities panel."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QLabel, QGridLayout,
)
from ..i18n.manager import I18nManager


class DevicePanel(QWidget):
    """Displays connected device information and capabilities."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Device info group
        info_group = QGroupBox(I18nManager.get("device.title"))
        info_grid = QGridLayout(info_group)
        fields = [
            "device.model", "device.firmware", "device.protocol",
            "device.serial", "device.interface",
        ]
        for i, key in enumerate(fields):
            info_grid.addWidget(QLabel(I18nManager.get(key)), i, 0, Qt.AlignRight)
            val = QLabel("-")
            val.setStyleSheet("font-weight: bold;")
            info_grid.addWidget(val, i, 1)
            self._value_labels[key] = val
        layout.addWidget(info_group)

        # Capabilities group
        cap_group = QGroupBox(I18nManager.get("device.capabilities"))
        cap_grid = QGridLayout(cap_group)
        cap_fields = [
            "device.adc_yes", "device.usb_yes",
            "device.multi_can", "device.can_count",
        ]
        for i, key in enumerate(cap_fields):
            cap_grid.addWidget(QLabel(I18nManager.get(key)), i, 0, Qt.AlignRight)
            val = QLabel("-")
            val.setStyleSheet("font-weight: bold;")
            cap_grid.addWidget(val, i, 1)
            self._value_labels[key] = val
        layout.addWidget(cap_group)
        layout.addStretch()

    def update_device_info(self, info: dict):
        """Update from parsed device info."""
        self._set("device.model", info.get("mcu_model", "-"))
        self._set("device.firmware", info.get("fw_version", "-"))
        self._set("device.protocol", info.get("protocol_version", "-"))
        self._set("device.serial", info.get("device_serial", "-"))

    def update_capabilities(self, caps: dict):
        """Update from parsed capabilities."""
        self._set("device.adc_yes",
                  I18nManager.get("device.adc_yes") if caps.get("has_adc") else I18nManager.get("device.adc_no"))
        self._set("device.usb_yes",
                  I18nManager.get("device.usb_yes") if caps.get("has_usb_cdc") else I18nManager.get("device.usb_no"))
        self._set("device.multi_can",
                  I18nManager.get("device.multi_can") if caps.get("has_multi_can") else "-")
        self._set("device.can_count", str(caps.get("can_channel_count", "-")))

    def update_interface(self, iface: str):
        self._set("device.interface", iface)

    def _set(self, key: str, value: str):
        if key in self._value_labels:
            self._value_labels[key].setText(str(value))

    def clear(self):
        for label in self._value_labels.values():
            label.setText("-")
