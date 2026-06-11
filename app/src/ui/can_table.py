"""CAN message table with filtering, export, and color-coded rows."""
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, Slot, QTimer
from PySide6.QtGui import QColor, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QLineEdit, QPushButton, QCheckBox, QFileDialog, QLabel,
)
from ..i18n.manager import I18nManager
from ..protocol.command_builder import CommandBuilder
from .styles import CAN_COLORS

_COLUMNS = ["#", "timestamp", "can_id", "type", "dlc", "data", "channel", "flags"]
_COLUMN_KEYS = ["index", "timestamp", "can_id", "type_str", "dlc", "data_hex", "channel", "flags_str"]


class CANMessageTableModel(QAbstractTableModel):
    """Model holding CAN message rows for QTableView."""

    def __init__(self, max_rows: int = 10000):
        super().__init__()
        self._rows: list[dict] = []
        self._max_rows = max_rows
        self._counter = 0
        self._paused = False
        self._dark_theme = True
        self._filter_text = ""
        self._filter_error_only = False
        self._filter_id = None  # specific CAN ID to filter
        self._visible_rows: list[dict] = []

    def set_dark_theme(self, dark: bool):
        self._dark_theme = dark

    def add_frame(self, frame: dict):
        """Add a parsed CAN frame to the table."""
        if self._paused:
            return
        self._counter += 1
        frame["index"] = self._counter
        # Compute display strings
        ide = frame.get("is_extended", False)
        rtr = frame.get("is_rtr", False)
        err = frame.get("is_error", False)
        if err:
            frame["type_str"] = "ERROR"
        elif rtr:
            frame["type_str"] = "EXT RTR" if ide else "STD RTR"
        else:
            frame["type_str"] = "EXT DATA" if ide else "STD DATA"
        frame["data_hex"] = " ".join(f"{b:02X}" for b in frame.get("data", b"")[:frame.get("dlc", 0)])
        flags = []
        if ide: flags.append("IDE")
        if rtr: flags.append("RTR")
        if err: flags.append("ERR")
        frame["flags_str"] = "|".join(flags) if flags else "-"
        self._rows.append(frame)
        # Enforce max rows
        while len(self._rows) > self._max_rows:
            self._rows.pop(0)
        self._rebuild_filter()

    def _rebuild_filter(self):
        """Rebuild visible rows based on current filter."""
        if not self._filter_text and not self._filter_error_only and self._filter_id is None:
            self._visible_rows = list(self._rows)
        else:
            self._visible_rows = []
            for row in self._rows:
                if self._filter_error_only and not row.get("is_error"):
                    continue
                if self._filter_id is not None and row.get("can_id") != self._filter_id:
                    continue
                if self._filter_text:
                    ft = self._filter_text.lower()
                    if ft == "error":
                        if not row.get("is_error"):
                            continue
                    else:
                        # Try to match as hex ID
                        match = False
                        for key in _COLUMN_KEYS:
                            val = str(row.get(key, ""))
                            if ft in val.lower():
                                match = True
                                break
                        if not match:
                            continue
                self._visible_rows.append(row)
        self.modelReset.emit()

    def set_filter(self, text: str):
        self._filter_text = text.strip()
        self._filter_error_only = False
        self._filter_id = None
        if self._filter_text.lower() == "error":
            self._filter_error_only = True
        elif self._filter_text.startswith("0x"):
            try:
                self._filter_id = int(self._filter_text, 16)
            except ValueError:
                pass
        self._rebuild_filter()

    def clear(self):
        self._rows.clear()
        self._visible_rows.clear()
        self._counter = 0
        self.modelReset.emit()

    def set_paused(self, paused: bool):
        self._paused = paused

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def total_count(self) -> int:
        return self._counter

    # ---- QAbstractTableModel interface ----

    def rowCount(self, parent=QModelIndex()):
        return len(self._visible_rows)

    def columnCount(self, parent=QModelIndex()):
        return len(_COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            key = f"can_table.{_COLUMNS[section]}"
            return I18nManager.get(key)
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._visible_rows[index.row()]
        key = _COLUMN_KEYS[index.column()]
        val = row.get(key, "")

        if role == Qt.DisplayRole:
            return str(val)

        if role == Qt.ForegroundRole:
            # Color coding
            if row.get("is_error"):
                c = CAN_COLORS["error_fg_dark"] if self._dark_theme else CAN_COLORS["error_fg_light"]
                return QBrush(QColor(c))
            if row.get("is_extended"):
                c = CAN_COLORS["extended_fg_dark"] if self._dark_theme else CAN_COLORS["extended_fg_light"]
                return QBrush(QColor(c))
            if row.get("is_rtr"):
                c = CAN_COLORS["rtr_fg_dark"] if self._dark_theme else CAN_COLORS["rtr_fg_light"]
                return QBrush(QColor(c))
            return None

        if role == Qt.BackgroundRole:
            if row.get("is_error"):
                c = CAN_COLORS["error_bg_dark"] if self._dark_theme else CAN_COLORS["error_bg_light"]
                return QBrush(QColor(c))
            return None

        if role == Qt.TextAlignmentRole:
            if key in ("index", "dlc", "channel"):
                return Qt.AlignCenter
            if key == "timestamp":
                return Qt.AlignRight | Qt.AlignVCenter

        return None


class CANTableView(QWidget):
    """CAN message table with filter bar and action buttons."""

    frame_added = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = CANMessageTableModel()
        self._setup_ui()
        self._i18n = I18nManager._instance
        if self._i18n:
            self._i18n.changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Filter bar
        filter_layout = QHBoxLayout()
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText(I18nManager.get("can_table.filter_placeholder"))
        self._filter_edit.textChanged.connect(self._model.set_filter)
        filter_layout.addWidget(self._filter_edit)

        self._pause_btn = QPushButton(I18nManager.get("can_table.pause"))
        self._pause_btn.setCheckable(True)
        self._pause_btn.toggled.connect(self._on_pause)
        filter_layout.addWidget(self._pause_btn)

        self._clear_btn = QPushButton(I18nManager.get("can_table.clear"))
        self._clear_btn.clicked.connect(self._model.clear)
        filter_layout.addWidget(self._clear_btn)

        export_csv_btn = QPushButton("CSV")
        export_csv_btn.clicked.connect(self._export_csv)
        filter_layout.addWidget(export_csv_btn)

        layout.addLayout(filter_layout)

        # Table view
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.ExtendedSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 60)   # #
        self._table.setColumnWidth(1, 120)  # timestamp
        self._table.setColumnWidth(2, 90)   # can_id
        self._table.setColumnWidth(3, 80)   # type
        self._table.setColumnWidth(4, 40)   # dlc
        self._table.setColumnWidth(5, 250)  # data
        self._table.setColumnWidth(6, 40)   # channel
        self._table.setSortingEnabled(False)
        layout.addWidget(self._table)

    def _on_pause(self, checked):
        self._model.set_paused(checked)
        self._pause_btn.setText(I18nManager.get("can_table.pause") if not checked else "▶")

    def add_message(self, frame: dict):
        self._model.add_frame(frame)
        self.frame_added.emit(frame)

    def clear(self):
        self._model.clear()

    def row_count(self) -> int:
        return self._model.total_count

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "can_messages.csv", "CSV Files (*.csv)")
        if not path:
            return
        import csv
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([I18nManager.get(f"can_table.{c}") for c in _COLUMNS])
            for row in self._model._visible_rows:
                writer.writerow([row.get(k, "") for k in _COLUMN_KEYS])

    def _retranslate(self, lang):
        self._filter_edit.setPlaceholderText(I18nManager.get("can_table.filter_placeholder"))
        if not self._model.paused:
            self._pause_btn.setText(I18nManager.get("can_table.pause"))
        self._clear_btn.setText(I18nManager.get("can_table.clear"))

    def model(self):
        return self._model
