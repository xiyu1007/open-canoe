"""Statistics panel showing TX/RX/Error counts and rates."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QGridLayout,
)
from ..i18n.manager import I18nManager


class StatsPanel(QWidget):
    """Real-time CAN statistics display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tx_count = 0
        self._rx_count = 0
        self._error_count = 0
        self._tx_rate = 0.0
        self._rx_rate = 0.0
        self._prev_tx = 0
        self._prev_rx = 0
        self._setup_ui()
        # Rate update timer
        self._rate_timer = QTimer()
        self._rate_timer.timeout.connect(self._update_rates)
        self._rate_timer.start(1000)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        group = QGroupBox(I18nManager.get("stats.title"))
        grid = QGridLayout(group)

        labels = [
            ("stats.tx_frames", "0"),
            ("stats.rx_frames", "0"),
            ("stats.error_frames", "0"),
            ("stats.tx_rate", "0 f/s"),
            ("stats.rx_rate", "0 f/s"),
        ]
        self._value_labels = {}
        for i, (key, default) in enumerate(labels):
            grid.addWidget(QLabel(I18nManager.get(key)), i, 0, Qt.AlignRight)
            val_label = QLabel(default)
            val_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            val_label.setStyleSheet("font-weight: bold;")
            grid.addWidget(val_label, i, 1)
            self._value_labels[key] = val_label

        layout.addWidget(group)

        reset_btn = QPushButton(I18nManager.get("stats.reset"))
        reset_btn.clicked.connect(self.reset)
        layout.addWidget(reset_btn)
        layout.addStretch()

    def add_tx(self, count: int = 1):
        self._tx_count += count

    def add_rx(self, count: int = 1):
        self._rx_count += count

    def add_error(self, count: int = 1):
        self._error_count += count

    def _update_rates(self):
        self._tx_rate = self._tx_count - self._prev_tx
        self._rx_rate = self._rx_count - self._prev_rx
        self._prev_tx = self._tx_count
        self._prev_rx = self._rx_count
        self._value_labels["stats.tx_frames"].setText(str(self._tx_count))
        self._value_labels["stats.rx_frames"].setText(str(self._rx_count))
        self._value_labels["stats.error_frames"].setText(str(self._error_count))
        self._value_labels["stats.tx_rate"].setText(f"{self._tx_rate} f/s")
        self._value_labels["stats.rx_rate"].setText(f"{self._rx_rate} f/s")

    def reset(self):
        self._tx_count = 0
        self._rx_count = 0
        self._error_count = 0
        self._tx_rate = 0.0
        self._rx_rate = 0.0
        self._prev_tx = 0
        self._prev_rx = 0
        self._update_rates()
