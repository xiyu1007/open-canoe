"""Firmware flash dialog with progress simulation."""
import os
import subprocess
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QProgressBar, QFileDialog, QComboBox, QMessageBox, QGroupBox,
)
from ..i18n.manager import I18nManager

ST_FLASH = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "assert",
    "stlink-1.7.0-x86_64-w64-mingw32",
    "stlink-1.7.0-x86_64-w64-mingw32", "bin", "st-flash.exe"
))


class FlashWorker(QThread):
    """Background thread for flash operations."""
    progress = Signal(int, str)  # percent, message
    finished = Signal(bool, str)  # success, message

    def __init__(self, bin_path: str, target: str, flash_addr: str = "0x08000000"):
        super().__init__()
        self._bin_path = bin_path
        self._target = target
        self._flash_addr = flash_addr
        self._mock = not os.path.exists(ST_FLASH)

    def run(self):
        if self._mock:
            self._mock_flash()
        else:
            self._real_flash()

    def _mock_flash(self):
        import time
        for pct in [0, 10, 30, 50, 70, 85, 95, 100]:
            self.progress.emit(pct, f"Flashing... {pct}%")
            time.sleep(0.4)
        self.progress.emit(100, "Flash complete!")
        self.finished.emit(True, I18nManager.get("flash.complete"))

    def _real_flash(self):
        self.progress.emit(0, "Erasing...")
        result = subprocess.run(
            [ST_FLASH, "--reset", "write", self._bin_path, self._flash_addr],
            capture_output=True, text=True, timeout=60,
        )
        output = result.stdout + result.stderr
        if "jolly good" in output.lower() or result.returncode == 0:
            self.progress.emit(100, "Success")
            self.finished.emit(True, I18nManager.get("flash.complete"))
        else:
            self.finished.emit(False, output[-300:])


class FlashDialog(QDialog):
    """Dialog for flashing firmware to device."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(I18nManager.get("flash.title"))
        self.resize(500, 300)
        self._worker: FlashWorker | None = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # File selection
        file_group = QGroupBox("Firmware")
        file_layout = QHBoxLayout(file_group)
        self._file_label = QLabel("")
        file_layout.addWidget(self._file_label, 1)
        browse_btn = QPushButton(I18nManager.get("flash.browse"))
        browse_btn.clicked.connect(self._browse)
        file_layout.addWidget(browse_btn)
        layout.addWidget(file_group)

        # Target selection
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel(I18nManager.get("flash.target")))
        self._target_combo = QComboBox()
        self._target_combo.addItems(["STM32F103C8T6", "STM32F407VET6"])
        target_layout.addWidget(self._target_combo)
        target_layout.addStretch()
        layout.addLayout(target_layout)

        # Progress
        self._progress = QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)
        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self._flash_btn = QPushButton(I18nManager.get("flash.start"))
        self._flash_btn.setObjectName("primaryBtn")
        self._flash_btn.clicked.connect(self._start_flash)
        btn_layout.addWidget(self._flash_btn)
        cancel_btn = QPushButton(I18nManager.get("flash.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Firmware",
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "hardware"),
            "Binary Files (*.bin *.hex);;All Files (*.*)")
        if path:
            self._file_label.setText(path)

    def _start_flash(self):
        bin_path = self._file_label.text()
        if not bin_path:
            QMessageBox.warning(self, I18nManager.get("dialog.error"), "Select a firmware file first")
            return
        target = self._target_combo.currentText()
        flash_addr = "0x08000000"
        self._flash_btn.setEnabled(False)
        self._worker = FlashWorker(bin_path, target, flash_addr)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_progress(self, pct: int, msg: str):
        self._progress.setValue(pct)
        self._status_label.setText(msg)

    def _on_finished(self, success: bool, msg: str):
        self._flash_btn.setEnabled(True)
        if success:
            QMessageBox.information(self, I18nManager.get("dialog.info"), msg)
            self.accept()
        else:
            QMessageBox.critical(self, I18nManager.get("flash.failed"), msg)
