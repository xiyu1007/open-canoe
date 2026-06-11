"""Waveform display window for ADC and logic-level data."""
from collections import deque
import struct
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QCheckBox,
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

from ..i18n.manager import I18nManager
from ..protocol.protocol_defs import Command


class WaveformPlot(QWidget):
    """Simple real-time waveform plot using QPainter."""

    def __init__(self, max_points: int = 2000, parent=None):
        super().__init__(parent)
        self._max_points = max_points
        self._data: deque[float] = deque(maxlen=max_points)
        self._time: deque[int] = deque(maxlen=max_points)
        self._t_offset = 0
        self._running = False
        self._y_min = 0
        self._y_max = 4095
        self._zoom_x = 1.0
        self._offset_x = 0.0
        self.setMinimumHeight(200)
        self.setMouseTracking(True)

    def set_y_range(self, y_min: int, y_max: int):
        self._y_min = y_min
        self._y_max = y_max

    def add_samples(self, samples: list[int], t_start: int, sample_rate: int):
        dt_us = 1_000_000.0 / max(sample_rate, 1)
        for i, val in enumerate(samples):
            t_us = t_start + int(i * dt_us)
            self._data.append(float(val))
            self._time.append(t_us)
        while len(self._data) > self._max_points:
            self._data.popleft()
            self._time.popleft()
        self._t_offset = self._time[0] if self._time else 0
        self.update()

    def clear(self):
        self._data.clear()
        self._time.clear()
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        margin = 40
        pw, ph = w - 2 * margin, h - 2 * margin

        # Background
        painter.fillRect(0, 0, w, h, QColor("#1e1e2e"))
        # Grid
        pen = QPen(QColor("#313244"), 1, Qt.DashLine)
        painter.setPen(pen)
        for i in range(5):
            y = margin + ph * i // 4
            painter.drawLine(margin, y, w - margin, y)
        for i in range(5):
            x = margin + pw * i // 4
            painter.drawLine(x, margin, x, h - margin)

        # Y axis labels
        painter.setPen(QColor("#a6adc8"))
        font = QFont("Consolas", 8)
        painter.setFont(font)
        for i in range(5):
            val = self._y_max - (self._y_max - self._y_min) * i / 4
            y = margin + ph * i // 4
            painter.drawText(2, y + 4, f"{val:.0f}")

        # Waveform
        if len(self._data) < 2:
            painter.end()
            return

        data_list = list(self._data)
        y_span = max(self._y_max - self._y_min, 1)

        pen = QPen(QColor("#89b4fa"), 1.5)
        painter.setPen(pen)
        path = QPainterPath()
        first_x = margin
        first_y = margin + ph - (data_list[0] - self._y_min) / y_span * ph
        path.moveTo(first_x, first_y)

        for i in range(1, len(data_list)):
            x = margin + (i / max(len(data_list) - 1, 1)) * pw
            y = margin + ph - (data_list[i] - self._y_min) / y_span * ph
            path.lineTo(x, y)

        painter.drawPath(path)
        painter.end()


class WaveformWindow(QWidget):
    """Standalone waveform display window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(I18nManager.get("waveform.title"))
        self.resize(800, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Controls
        ctrl = QHBoxLayout()
        self._start_btn = QPushButton(I18nManager.get("waveform.start"))
        ctrl.addWidget(self._start_btn)
        self._stop_btn = QPushButton(I18nManager.get("waveform.stop"))
        self._stop_btn.setEnabled(False)
        ctrl.addWidget(self._stop_btn)

        ctrl.addWidget(QLabel(I18nManager.get("waveform.mode_adc")))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems([
            I18nManager.get("waveform.mode_adc"),
            I18nManager.get("waveform.mode_logic"),
        ])
        ctrl.addWidget(self._mode_combo)

        self._auto_range_cb = QCheckBox(I18nManager.get("waveform.auto_range"))
        self._auto_range_cb.setChecked(True)
        ctrl.addWidget(self._auto_range_cb)

        ctrl.addStretch()
        layout.addLayout(ctrl)

        # Plot
        self._plot = WaveformPlot()
        layout.addWidget(self._plot)

        # Status
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    def add_adc_packet(self, packet: dict):
        """Add ADC waveform data packet."""
        samples = packet.get("samples", [])
        if samples:
            self._plot.add_samples(
                samples,
                packet.get("timestamp", 0),
                packet.get("sample_rate", 100000),
            )
            self._status_label.setText(
                f"Samples: {len(samples)} | Rate: {packet.get('sample_rate', 0)} Hz"
            )

    def clear(self):
        self._plot.clear()
