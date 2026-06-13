"""历史报文查看窗口 — 搜索、过滤、分页加载 CSV 格式的历史报文。"""
from __future__ import annotations

import csv, os, time, tkinter as tk
from tkinter import ttk
from gui.config import *
from gui.lang import L


HISTORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "history")


class HistoryWindow(tk.Toplevel):
    """可搜索/过滤的历史报文弹窗，从 CSV 文件加载。"""

    def __init__(self, parent, filepath: str = ""):
        super().__init__(parent)
        L_ = L()
        self.title(L_["history_title"] if "history_title" in L_ else "History Messages")
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
        cols = (L_["col_no"], L_["col_time"], L_["col_id"], L_["col_type"],
                L_["col_dlc"], L_["col_ch"], L_["col_data"])
        self._tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="extended")
        for col in cols:
            self._tree.heading(col, text=col, anchor=tk.W)
            self._tree.column(col, width=100, minwidth=50, stretch=(col == L_["col_data"]))
        vsb = ttk.Scrollbar(tf, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns")
        tf.grid_rowconfigure(0, weight=1); tf.grid_columnconfigure(0, weight=1)

        if filepath and os.path.exists(filepath):
            self._load(filepath)
        elif os.path.isdir(HISTORY_DIR):
            self._show_file_list()

    def _show_file_list(self) -> None:
        """If no specific file, show list of history files."""
        files = sorted([f for f in os.listdir(HISTORY_DIR) if f.endswith(".csv")], reverse=True)
        if not files:
            self._tree.insert("", tk.END, values=("No history files found",))
            return
        for f in files:
            path = os.path.join(HISTORY_DIR, f)
            size = os.path.getsize(path)
            self._tree.insert("", tk.END, values=(f, f"{size:,} bytes", "", "", "", ""))

    def _load(self, filepath: str) -> None:
        """Load all rows from CSV into memory."""
        self._filepath = filepath
        self._all_rows.clear()
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                for row in reader:
                    if len(row) >= 7:
                        self._all_rows.append(row[:7])
        except Exception:
            pass
        self._apply_filter()

    def _apply_filter(self) -> None:
        """Rebuild tree from filtered rows."""
        search = self._search_var.get().lower().strip()
        id_filter = self._id_var.get().lower().strip()
        dir_filter = self._dir_var.get()

        self._filtered.clear()
        for row in self._all_rows:
            if id_filter and id_filter not in row[2].lower():
                continue
            if dir_filter != "All" and (len(row) < 6 or row[5] != dir_filter):
                continue
            if search:
                match = False
                for col in row:
                    if search in col.lower():
                        match = True
                        break
                if not match:
                    continue
            self._filtered.append(row)

        self._tree.delete(*self._tree.get_children())
        # Cap display at 5000 for performance
        visible = self._filtered if len(self._filtered) <= 5000 else self._filtered[-5000:]
        for i, row in enumerate(visible):
            self._tree.insert("", tk.END, values=row)
        total = len(self._all_rows)
        shown = len(self._filtered)
        if shown != total:
            self._info_lbl.config(text=f"Showing {min(shown, 5000)} / {shown} filtered ({total} total)")
        else:
            self._info_lbl.config(text=f"{shown} messages")
