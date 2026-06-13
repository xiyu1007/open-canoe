"""历史报文查看窗口 — 搜索、过滤，合并当前内存报文 + CSV 历史报文。"""
from __future__ import annotations

import csv, os, tkinter as tk
from tkinter import ttk
from gui.config import *
from gui.lang import L


_HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "history")


class HistoryWindow(tk.Toplevel):
    """显示所有报文（当前 + 已卸出到 CSV 的历史），支持搜索/过滤。"""

    def __init__(self, parent, filepath: str = "", current_messages=None):
        super().__init__(parent)
        L_ = L()
        self.title(L_.get("history_title", "History Messages"))
        self.geometry("1000x550")
        self._filepath = filepath
        self._all_rows: list[list[str]] = []
        self._filtered: list[list[str]] = []

        # Search bar
        bar = ttk.Frame(self, padding=(8, 8))
        bar.pack(fill=tk.X)
        ttk.Label(bar, text=L_.get("search", "Search")).pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        se = ttk.Entry(bar, textvariable=self._search_var, font=FONT_BODY, width=30)
        se.pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(bar, text="ID").pack(side=tk.LEFT)
        self._id_var = tk.StringVar()
        self._id_var.trace_add("write", lambda *_: self._apply_filter())
        ie = ttk.Entry(bar, textvariable=self._id_var, font=FONT_BODY, width=10)
        ie.pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(bar, text=L_.get("col_ch", "Dir")).pack(side=tk.LEFT)
        self._dir_var = tk.StringVar(value="All")
        dc = ttk.Combobox(bar, textvariable=self._dir_var, values=["All", "TX", "RX"],
                          state="readonly", font=FONT_BODY, width=4)
        dc.pack(side=tk.LEFT, padx=(4, 12))
        dc.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        self._info_lbl = ttk.Label(bar, text="", foreground=SECONDARY, font=FONT_HINT)
        self._info_lbl.pack(side=tk.RIGHT)

        # Tree
        tf = ttk.Frame(self, padding=(8, 0))
        tf.pack(fill=tk.BOTH, expand=True)
        cols = (L_["col_time"], L_["col_id"], L_["col_type"],
                L_["col_dlc"], L_["col_ch"], L_["col_data"])
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        for col in cols:
            self._tree.heading(col, text=col, anchor=tk.W)
            self._tree.column(col, width=100, minwidth=50, stretch=(col == L_["col_data"]))
        vsb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        tf.grid_rowconfigure(0, weight=1); tf.grid_columnconfigure(0, weight=1)

        # Load CSV history first, then append current in-memory messages
        if filepath and os.path.exists(filepath):
            self._load_csv(filepath)
        # Convert current messages to rows and append
        if current_messages:
            L_ = L()
            for msg, is_tx, ts in current_messages:
                txrx = "TX" if is_tx else "RX"
                dtype = "ERR" if msg.is_error else ("EXT" if msg.is_extended else "STD")
                self._all_rows.append([ts, msg.id_str, dtype, str(msg.dlc), txrx, msg.data_str])
        # If nothing loaded, show file list
        if not self._all_rows and os.path.isdir(_HISTORY_DIR):
            self._show_file_list()
        self._apply_filter()

    def _show_file_list(self) -> None:
        """If no data at all, show list of history CSV files."""
        if not os.path.isdir(_HISTORY_DIR):
            self._tree.insert("", tk.END, values=("No history files found",))
            return
        files = sorted([f for f in os.listdir(_HISTORY_DIR) if f.endswith(".csv")], reverse=True)
        if not files:
            self._tree.insert("", tk.END, values=("No history files found",))
            return
        for f in files:
            path = os.path.join(_HISTORY_DIR, f)
            size = os.path.getsize(path)
            self._tree.insert("", tk.END, values=(f, f"{size:,} bytes", "", "", "", ""))

    def _load_csv(self, filepath: str) -> None:
        """Load CSV rows (skipping header)."""
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                first = True
                for row in reader:
                    if first and row and row[0].startswith("#"):
                        first = False
                        continue
                    first = False
                    if len(row) >= 7:
                        self._all_rows.append(row[:7])
                    elif len(row) >= 6:
                        self._all_rows.append(row[:6])
        except Exception:
            pass

    def _apply_filter(self) -> None:
        """Rebuild tree from filtered rows."""
        search = self._search_var.get().lower().strip()
        id_filter = self._id_var.get().lower().strip()
        dir_filter = self._dir_var.get()

        self._filtered.clear()
        for row in self._all_rows:
            # Normalize: CSV rows have 7 cols (with seq), current has 6 cols
            # After normalization: [time, id, type, dlc, dir, data]
            if len(row) >= 7:
                norm = row[1:7]  # skip seq column from CSV
            else:
                norm = row[:6]
            if id_filter and id_filter not in (norm[1] if len(norm) > 1 else "").lower():
                continue
            if dir_filter != "All" and (len(norm) < 5 or norm[4] != dir_filter):
                continue
            if search:
                match = False
                for col in norm:
                    if search in col.lower():
                        match = True
                        break
                if not match:
                    continue
            self._filtered.append(norm)

        self._tree.delete(*self._tree.get_children())
        visible = self._filtered if len(self._filtered) <= 5000 else self._filtered[-5000:]
        for row in visible:
            self._tree.insert("", tk.END, values=row)
        total = len(self._all_rows)
        shown = len(self._filtered)
        if shown != total:
            self._info_lbl.config(text=f"Showing {min(shown, 5000)} / {shown} filtered ({total} total)")
        else:
            self._info_lbl.config(text=f"{shown} messages")
