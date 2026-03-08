# views/monitoring.py
"""
Real-time sound-waveform monitoring view.
"""

import tkinter as tk

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class MonitoringView:
    def __init__(self, parent: tk.Frame) -> None:
        self.monitoring_view = tk.Frame(parent, bg="white")
        self._active = False
        self._build_ui()

    # ──────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────

    def _build_ui(self) -> None:
        tk.Label(
            self.monitoring_view,
            text="Real-Time Sound Acoustic Analysis",
            font=("Arial", 14, "bold"),
            bg="white",
        ).pack(pady=10)

        self._build_plot()
        self._build_controls()

    def _build_plot(self) -> None:
        self._fig, self._ax = plt.subplots(figsize=(10, 4), dpi=100)
        self._ax.set_title("Live Microphone Input", fontsize=12, fontweight="bold")
        self._ax.set_ylim(-1.0, 1.0)
        self._ax.set_xlabel("Time (samples)")
        self._ax.set_ylabel("Amplitude")
        self._ax.grid(True, alpha=0.3)

        (self._line,) = self._ax.plot(np.zeros(1_000), color="#27ae60", linewidth=0.8)

        self._canvas = FigureCanvasTkAgg(self._fig, master=self.monitoring_view)
        self._canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _build_controls(self) -> None:
        bar = tk.Frame(self.monitoring_view, bg="white")
        bar.pack(fill=tk.X, padx=10, pady=10)

        self._toggle_btn = tk.Button(
            bar,
            text="▶ Start Monitoring",
            command=self.toggle_monitoring,
            bg="#27ae60",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=20,
            pady=10,
        )
        self._toggle_btn.pack(side=tk.LEFT, padx=5)

        self._status_label = tk.Label(
            bar,
            text="Status: Stopped",
            font=("Arial", 11),
            bg="white",
            fg="#e74c3c",
        )
        self._status_label.pack(side=tk.LEFT, padx=20)

    # ──────────────────────────────────────────
    # Public interface
    # ──────────────────────────────────────────

    def toggle_monitoring(self) -> None:
        """Start or stop live waveform monitoring."""
        self._active = not self._active
        if self._active:
            self._toggle_btn.config(text="⏹ Stop Monitoring", bg="#e74c3c")
            self._status_label.config(text="Status: Recording…", fg="#27ae60")
        else:
            self._toggle_btn.config(text="▶ Start Monitoring", bg="#27ae60")
            self._status_label.config(text="Status: Stopped", fg="#e74c3c")

    def is_active(self) -> bool:
        """Return True while monitoring is enabled."""
        return self._active

    def update_line(self, signal: np.ndarray) -> None:
        """
        Redraw the waveform with *signal*.

        Safe to call from any thread (uses draw_idle).
        """
        if signal is None or len(signal) == 0:
            return
        self._line.set_ydata(signal)
        self._line.set_xdata(range(len(signal)))
        self._ax.set_xlim(0, len(signal))
        self._canvas.draw_idle()

    def get_frame(self) -> tk.Frame:
        return self.monitoring_view