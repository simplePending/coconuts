# views/dashboard.py
"""
Main dashboard view – camera feed on the left, status panel on the right.
"""

import tkinter as tk
from tkinter import ttk


class DashboardView:
    def __init__(self, parent: tk.Frame) -> None:
        self.main_view = tk.Frame(parent, bg="white")
        self._build_ui()

    # ──────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_camera_panel()
        self._build_status_panel()

    def _build_camera_panel(self) -> None:
        """Left column – live camera feed."""
        left = tk.Frame(self.main_view, bg="white")
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        tk.Label(
            left,
            text="Camera Feed — Coconut Detection",
            font=("Arial", 14, "bold"),
            bg="white",
        ).pack(pady=5)

        border = tk.Frame(left, bg="#34495e", highlightthickness=2)
        border.pack(fill=tk.BOTH, expand=True)

        self.video_label = tk.Label(border, bg="black")
        self.video_label.pack(padx=2, pady=2, fill=tk.BOTH, expand=True)

    def _build_status_panel(self) -> None:
        """Right column – status, counters, type breakdown."""
        right = tk.Frame(self.main_view, bg="#ecf0f1", width=300)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, padx=10, pady=10)
        right.pack_propagate(False)

        # ── Status ────────────────────────────
        self._section_header(right, "STATUS")

        self.status = tk.Label(
            right,
            text="Waiting for coconut…",
            font=("Arial", 16, "bold"),
            bg="white",
            fg="#2980b9",
            wraplength=280,
        )
        self.status.pack(fill=tk.X, pady=10, padx=5)

        self.process_status = tk.Label(
            right,
            text="",
            font=("Arial", 10),
            bg="white",
            fg="#7f8c8d",
            wraplength=280,
        )
        self.process_status.pack(fill=tk.X, pady=5, padx=5)

        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10, padx=5)

        # ── Counters ─────────────────────────
        self._section_header(right, "COUNTERS")

        self.counter = tk.Label(
            right,
            text="Total: 0\nCoconuts: 0",
            font=("Arial", 11),
            bg="white",
            justify=tk.LEFT,
        )
        self.counter.pack(fill=tk.X, pady=10, padx=5)

        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10, padx=5)

        # ── Type breakdown ───────────────────
        self._section_header(right, "TYPES")

        self.type_label = tk.Label(
            right,
            text="Malauhog: 0\nMalakatad: 0\nMalakanin: 0",
            font=("Arial", 11),
            bg="white",
            justify=tk.LEFT,
            fg="#27ae60",
        )
        self.type_label.pack(fill=tk.X, pady=10, padx=5)

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _section_header(parent: tk.Frame, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            font=("Arial", 12, "bold"),
            bg="#34495e",
            fg="white",
        ).pack(fill=tk.X, pady=(5, 10), padx=5)

    def get_frame(self) -> tk.Frame:
        return self.main_view