"""历史报文查看窗口 — 正则搜索、ID/Data/All 范围、合并当前+CSV 历史。"""
from __future__ import annotations

import csv, os, re, tkinter as tk
from tkinter import ttk
from gui.config import *
from gui.lang import L

_HISTORY_DIR = os.path.join(APP_DATA_DIR, HISTORY_DIR_NAME)


class HistoryWindow(tk.Toplevel):
    """正则搜索 + 范围过滤的历史报文窗口。"""

    def __init__(self, parent, filepath: str = "", current_messages=None):
        super().__init__(parent)
        L_ = L()
        self.title(L_.get("history_title", "History Messages"))
        self.geometry("1000x550")
        self._filepath = filepath
        self._current_msgs = current_messages  # saved for refresh
        self._all_rows: list[list[str]] = []
        self._filtered: list[list[str]] = []

        # Center on screen
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"+{x}+{y}")

        # ── Search bar ──
        bar = ttk.Frame(self, padding=(8, 8))
        bar.pack(fill=tk.X)

        # Scope dropdown
        self._scope_var = tk.StringVar(value="All")
        sc = ttk.Combobox(bar, textvariable=self._scope_var, values=["All", "ID", "Data"],
                          state="readonly", font=FONT_BODY, width=5)
        sc.pack(side=tk.LEFT, padx=(0, 4))
        sc.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        # Search entry with placeholder
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(bar, textvariable=self._search_var, font=FONT_BODY, width=32)
        self._search_entry.pack(side=tk.LEFT, padx=(0, 8))
        self._placeholder = L_.get("search_hint", "regex (ID|Data)")
        self._search_entry.insert(0, self._placeholder)
        self._search_entry.config(foreground=TAG_MUTED)
        self._search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self._search_entry.bind("<FocusOut>", self._on_search_focus_out)
        self._search_var.trace_add("write", lambda *_: self._apply_filter())

        # Regex toggle
        self._regex_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text=".*", variable=self._regex_var,
                        command=self._apply_filter).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(bar, text=L_.get("col_ch", "Dir")).pack(side=tk.LEFT)
        self._dir_var = tk.StringVar(value="All")
        dc = ttk.Combobox(bar, textvariable=self._dir_var, values=["All", "TX", "RX"],
                          state="readonly", font=FONT_BODY, width=4)
        dc.pack(side=tk.LEFT, padx=(4, 12))
        dc.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        ttk.Label(bar, text=L_.get("col_type", "Type")).pack(side=tk.LEFT, padx=(12, 4))
        self._type_var = tk.StringVar(value="All")
        tc = ttk.Combobox(bar, textvariable=self._type_var,
                          values=["All", "STD", "EXT", "RTR_STD", "RTR_EXT", "ERR"],
                          state="readonly", font=FONT_BODY, width=8)
        tc.pack(side=tk.LEFT, padx=(0, 12))
        tc.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        ttk.Button(bar, text="⟳", width=3, command=self._refresh).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(bar, text="Export", command=self._export).pack(side=tk.RIGHT, padx=(12, 0))
        self._info_lbl = ttk.Label(bar, text="", foreground=SECONDARY, font=FONT_HINT)
        self._info_lbl.pack(side=tk.RIGHT)

        # ── Tree ──
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

        # ── Load data ──
        if filepath and os.path.exists(filepath):
            self._load_csv(filepath)
        if current_messages:
            for msg, is_tx, ts in current_messages:
                txrx = "TX" if is_tx else "RX"
                if msg.is_error: dt = "ERR"
                elif msg.is_remote and msg.is_extended: dt = "RTR_EXT"
                elif msg.is_remote: dt = "RTR_STD"
                elif msg.is_extended: dt = "EXT"
                else: dt = "STD"
                self._all_rows.append([ts, msg.id_str, dt, str(msg.dlc), txrx, msg.data_str])
        if not self._all_rows and os.path.isdir(_HISTORY_DIR):
            self._show_file_list()
        self._apply_filter()

    def _on_search_focus_in(self, _e):
        if self._search_var.get() == self._placeholder:
            self._search_var.set("")
            self._search_entry.config(foreground=PRIMARY)

    def _on_search_focus_out(self, _e):
        if not self._search_var.get().strip():
            self._search_var.set(self._placeholder)
            self._search_entry.config(foreground=TAG_MUTED)

    def _refresh(self) -> None:
        """Re-load from CSV and current messages without closing window."""
        self._all_rows.clear()
        if self._filepath and os.path.exists(self._filepath):
            self._load_csv(self._filepath)
        if self._current_msgs:
            for msg, is_tx, ts in self._current_msgs:
                txrx = "TX" if is_tx else "RX"
                if msg.is_error: dt = "ERR"
                elif msg.is_remote and msg.is_extended: dt = "RTR_EXT"
                elif msg.is_remote: dt = "RTR_STD"
                elif msg.is_extended: dt = "EXT"
                else: dt = "STD"
                self._all_rows.append([ts, msg.id_str, dt, str(msg.dlc), txrx, msg.data_str])
        self._apply_filter()

    def _export(self) -> None:
        """Export filtered rows to a CSV file."""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".csv", filetypes=[("CSV", "*.csv")],
            initialfile=f"canoe_export_{__import__('time').strftime('%Y%m%d_%H%M%S')}.csv")
        # Bring history window back to front after file dialog closes
        self.lift()
        self.focus_force()
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                for row in self._filtered:
                    w.writerow(row)
            self._info_lbl.config(text=f"Exported {len(self._filtered)} rows")
        except Exception as e:
            self._info_lbl.config(text=f"Export error: {e}")

    def _show_file_list(self) -> None:
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
        try:
            with open(filepath, "r", encoding="utf-8") as fh:
                reader = csv.reader(fh)
                first = True
                for row in reader:
                    if first and row and not row[0].startswith("0x"):
                        first = False; continue
                    first = False
                    if len(row) >= 7:
                        self._all_rows.append(row[1:7])
                    elif len(row) >= 6:
                        self._all_rows.append(row[:6])
        except Exception:
            pass

    def _apply_filter(self) -> None:
        search_raw = self._search_var.get().strip()
        if search_raw == self._placeholder:
            search_raw = ""
        scope = self._scope_var.get()
        dir_filter = self._dir_var.get()
        type_filter = self._type_var.get()
        use_regex = self._regex_var.get()

        # Compile regex if needed
        pattern = None
        if search_raw and use_regex:
            try:
                pattern = re.compile(search_raw, re.IGNORECASE)
            except re.error:
                pattern = None

        self._filtered.clear()
        for row in self._all_rows:
            # row: [time, id, type, dlc, dir, data]
            if dir_filter != "All" and (len(row) < 5 or row[4] != dir_filter):
                continue
            if type_filter != "All" and (len(row) < 3 or row[2] != type_filter):
                continue
            if search_raw:
                if use_regex and pattern:
                    match = False
                    if scope in ("All", "ID") and len(row) > 1 and pattern.search(row[1]):
                        match = True
                    if scope in ("All", "Data") and len(row) > 5 and pattern.search(row[5]):
                        match = True
                    if not match:
                        continue
                else:
                    # Plain text search
                    search_lower = search_raw.lower()
                    match = False
                    if scope in ("All", "ID") and len(row) > 1 and search_lower in row[1].lower():
                        match = True
                    if scope in ("All", "Data") and len(row) > 5 and search_lower in row[5].lower():
                        match = True
                    if not match:
                        continue
            self._filtered.append(row)

        self._tree.delete(*self._tree.get_children())
        visible = self._filtered if len(self._filtered) <= 5000 else self._filtered[-5000:]
        for row in visible:
            self._tree.insert("", tk.END, values=row)
        total = len(self._all_rows)
        shown = len(self._filtered)
        if shown != total:
            self._info_lbl.config(text=f"{min(shown, 5000)}/{shown} ({total} total)")
        else:
            self._info_lbl.config(text=f"{shown} messages")
