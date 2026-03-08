# views/history.py
"""
Data history view – date-range filter, trend graph, sortable table, CSV export.
"""

import logging
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import ttk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from data_manager import aggregate_by_date, export_to_csv, get_data_by_date_range

logger = logging.getLogger(__name__)


class HistoryView:
    def __init__(self, parent: tk.Frame) -> None:
        self.history_view = tk.Frame(parent, bg="white")
        self._records: list[dict] = []
        self._build_ui()

    # ──────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_filter_bar()
        self._build_graph()
        self._build_table()
        self._build_export_button()

    def _build_filter_bar(self) -> None:
        bar = tk.Frame(self.history_view, bg="#ecf0f1")
        bar.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(
            bar, text="Data History", font=("Arial", 14, "bold"), bg="#ecf0f1"
        ).pack(side=tk.LEFT, padx=10, pady=10)

        picker = tk.Frame(bar, bg="white")
        picker.pack(side=tk.LEFT, padx=10, pady=5)

        tk.Label(picker, text="From:", bg="white").pack(side=tk.LEFT, padx=5)
        self._date_from = tk.Entry(picker, width=15)
        self._date_from.insert(0, (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
        self._date_from.pack(side=tk.LEFT, padx=5)

        tk.Label(picker, text="To:", bg="white").pack(side=tk.LEFT, padx=5)
        self._date_to = tk.Entry(picker, width=15)
        self._date_to.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self._date_to.pack(side=tk.LEFT, padx=5)

        tk.Button(
            picker,
            text="PULL DATA",
            command=self.pull_data,
            bg="#27ae60",
            fg="white",
            font=("Arial", 10, "bold"),
            padx=20,
            pady=5,
        ).pack(side=tk.LEFT, padx=10)

    def _build_graph(self) -> None:
        frame = tk.Frame(self.history_view, bg="white")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(
            frame, text="Sorting Trends", font=("Arial", 12, "bold"), bg="white"
        ).pack(anchor="w", padx=10, pady=5)

        self._fig, self._ax = plt.subplots(figsize=(10, 3), dpi=100)
        self._ax.set_title("Coconut Sorting Trends", fontsize=11, fontweight="bold")
        self._ax.set_xlabel("Date")
        self._ax.set_ylabel("Count")
        self._ax.grid(True, alpha=0.3)

        self._canvas = FigureCanvasTkAgg(self._fig, master=frame)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _build_table(self) -> None:
        frame = tk.Frame(self.history_view, bg="white")
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(
            frame, text="Sorting Records", font=("Arial", 12, "bold"), bg="white"
        ).pack(anchor="w", padx=5, pady=5)

        columns = ("Date", "Time", "Malauhog", "Malakatad", "Malakanin")
        self._tree = ttk.Treeview(frame, columns=columns, height=8, show="headings")
        for col in columns:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=110, anchor="center")
        self._tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_export_button(self) -> None:
        tk.Button(
            self.history_view,
            text="📥 Export to CSV",
            command=self._export_csv,
            bg="#3498db",
            fg="white",
            font=("Arial", 11, "bold"),
            padx=20,
            pady=8,
        ).pack(pady=10)

    # ──────────────────────────────────────────
    # Data operations
    # ──────────────────────────────────────────

    def pull_data(self) -> None:
        """Fetch records for the selected date range and refresh the UI."""
        try:
            start = datetime.strptime(self._date_from.get(), "%Y-%m-%d").date()
            end   = datetime.strptime(self._date_to.get(),   "%Y-%m-%d").date()
        except ValueError:
            logger.error("Invalid date format – expected YYYY-MM-DD")
            return

        self._records = get_data_by_date_range(start, end)
        self._refresh_graph()
        self._refresh_table()

    def _refresh_graph(self) -> None:
        aggregated = aggregate_by_date(self._records)
        self._ax.clear()

        if not aggregated:
            self._ax.set_title("No data for selected range")
            self._canvas.draw_idle()
            return

        dates = sorted(aggregated.keys())
        malauhog  = [aggregated[d]["Malauhog"]  for d in dates]
        malakatad = [aggregated[d]["Malakatad"] for d in dates]
        malakanin = [aggregated[d]["Malakanin"] for d in dates]

        self._ax.plot(dates, malauhog,  marker="o", label="Malauhog",  color="#27ae60")
        self._ax.plot(dates, malakatad, marker="s", label="Malakatad", color="#2980b9")
        self._ax.plot(dates, malakanin, marker="^", label="Malakanin", color="#8e44ad")
        self._ax.set_title("Coconut Sorting Trends", fontsize=11, fontweight="bold")
        self._ax.set_xlabel("Date")
        self._ax.set_ylabel("Count")
        self._ax.legend()
        self._ax.grid(True, alpha=0.3)
        self._fig.tight_layout()
        self._canvas.draw_idle()

    def _refresh_table(self) -> None:
        for row in self._tree.get_children():
            self._tree.delete(row)

        # Aggregate per (date, time) bucket
        buckets: dict[tuple, dict] = {}
        for rec in self._records:
            key = (rec["date"], rec["time"])
            bucket = buckets.setdefault(key, {"Malauhog": 0, "Malakatad": 0, "Malakanin": 0})
            label_map = {"MALAUHOG": "Malauhog", "MALAKATAD": "Malakatad", "MALAKANIN": "Malakanin"}
            display = label_map.get(rec["type"])
            if display:
                bucket[display] += 1

        for (date, t), counts in sorted(buckets.items(), reverse=True):
            self._tree.insert(
                "", "end",
                values=(date, t, counts["Malauhog"], counts["Malakatad"], counts["Malakanin"]),
            )

    def _export_csv(self) -> None:
        if export_to_csv(self._records):
            logger.info("Exported %d records to CSV", len(self._records))
        else:
            logger.error("CSV export failed")

    # ──────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────

    def get_frame(self) -> tk.Frame:
        return self.history_view