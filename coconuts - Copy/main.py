# main.py
"""
Coconut Sorting System – main application entry point.

Architecture
------------
- Camera loop   : Tkinter after() callback – never blocks the UI thread
- Serial waits  : background daemon threads via threading.Thread
- Audio capture : sounddevice (blocking sd.wait() runs in its own thread)
- Storage       : SQLite via data_manager (thread-safe writes)
"""

import logging
import threading
import time
from collections import deque

import cv2
import numpy as np
import sounddevice as sd
from PIL import Image, ImageTk

# Matplotlib TkAgg backend must be set before any other matplotlib import
import matplotlib
matplotlib.use("TkAgg")

import tkinter as tk
from tkinter import ttk

from vision import detect_coconut, select_model
from sound_analyzer import analyze_tap
from serial_comm import (
    connect_port, disconnect_port, drain_serial, init_serial,
    list_serial_ports, route_coconut, send, start_motor, stop_motor,
    tap_coconut, wait_for_detection, wait_for_routing_complete, wait_for_tap_done,
)
from data_manager import add_record
from views.dashboard import DashboardView
from views.monitoring import MonitoringView
from views.history import HistoryView

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── label normalisation ───────────────────────────────────────────────────────
_CAMERA_TO_LABEL = {
    "Mature":    "MALAUHOG",
    "Potential": "MALAKATAD",
    "Premature": "MALAKANIN",
}

def _normalize(value: str) -> str:
    """Return a canonical MALAUHOG / MALAKATAD / MALAKANIN label."""
    return _CAMERA_TO_LABEL.get(value, value)


# ══════════════════════════════════════════════════════════════════════════════
class CoconutSorter:
    """Main application controller."""

    # ── tuneable constants ────────────────────────────────────────────────────
    CAMERA_INDEX        = 1         # OpenCV camera device index
    FRAME_W, FRAME_H   = 640, 480
    CAMERA_POLL_MS      = 30        # ~33 fps (ms between camera frames)
    MONITOR_POLL_MS     = 100       # audio monitoring interval
    STABILITY_THRESHOLD = 4.0       # seconds a detection must persist
    IDLE_TIMEOUT        = 30.0      # auto-stop motor after this many idle seconds
    SOUND_ENERGY_MIN    = 12.0      # minimum FFT energy to trust sound classification
    ULTRASONIC_TIMEOUT  = 5.0       # seconds to wait for tap-sensor DETECTED message
    TAP_DONE_TIMEOUT    = 3.0       # seconds to wait for TAP_DONE
    ROUTING_TIMEOUT     = 10.0      # seconds — Arduino ROUTE_TIMEOUT_MS (8s) + headroom
    POST_ROUTE_DELAY    = 0.5       # seconds — brief drain pause before next cycle
    # ─────────────────────────────────────────────────────────────────────────

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Coconut Sorting System Dashboard")
        self.root.geometry("1200x800")

        init_serial()

        # ── counters ─────────────────────────────────────────────────────────
        self.total           = 0
        self.coconut_count   = 0
        self.malauhog_count  = 0
        self.malakatad_count = 0
        self.malakanin_count = 0

        # ── camera ───────────────────────────────────────────────────────────
        self.video = cv2.VideoCapture(self.CAMERA_INDEX)
        self.video.set(cv2.CAP_PROP_FRAME_WIDTH,  self.FRAME_W)
        self.video.set(cv2.CAP_PROP_FRAME_HEIGHT, self.FRAME_H)

        # ── detection state ───────────────────────────────────────────────────
        self._stable_type:  str | None = None
        self._stable_start: float | None = None

        # ── processing flags ─────────────────────────────────────────────────
        self.processing       = False
        self.motor_running    = False
        self._pending_maturity: str | None = None
        self._pending_conf    = 0.0
        self._idle_start: float | None = None

        # ── audio buffer for monitoring view ─────────────────────────────────
        self._audio_buf: deque[float] = deque(maxlen=8_820)

        # ── build UI then start loops ─────────────────────────────────────────
        self._build_nav()
        self._build_views()
        self._start_loops()

    # ══════════════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_nav(self) -> None:
        nav = tk.Frame(self.root, bg="#2c3e50", height=60)
        nav.pack(fill=tk.X, side=tk.TOP)
        nav.pack_propagate(False)

        def nav_btn(text, cmd, bg, side=tk.LEFT, **kw):
            tk.Button(
                nav, text=text, command=cmd,
                bg=bg, fg="white", font=("Arial", 11, "bold"),
                relief=tk.FLAT, padx=15, pady=8, **kw
            ).pack(side=side, padx=5)

        tk.Label(
            nav, text="🥥 COCONUT SORTING SYSTEM",
            font=("Arial", 18, "bold"), bg="#50e466", fg="white"
        ).pack(side=tk.LEFT, padx=20, pady=10)

        nav_btn("📊 Main Dashboard",  self._show_main,       "#3498db")
        nav_btn("🔊 Monitoring",      self._show_monitoring, "#27ae60")
        nav_btn("📈 Data History",    self._show_history,    "#e74c3c")

        self._btn_motor = tk.Button(
            nav, text="▶ START MOTOR", command=self._toggle_motor,
            bg="#2ecc71", fg="white", font=("Arial", 11, "bold"),
            relief=tk.FLAT, padx=15, pady=8,
        )
        self._btn_motor.pack(side=tk.LEFT, padx=5)

        # ── model loader ──────────────────────────────────────────────────────
        nav_btn("🤖 Load Model", self._load_model, "#f39c12", side=tk.RIGHT)
        self._model_label = tk.Label(
            nav, text="No model loaded",
            font=("Arial", 10), bg="#2c3e50", fg="#ecf0f1"
        )
        self._model_label.pack(side=tk.RIGHT, padx=10)

        # ── serial port controls ──────────────────────────────────────────────
        self._port_var  = tk.StringVar()
        self._port_combo = ttk.Combobox(nav, textvariable=self._port_var,
                                        state="readonly", width=12)
        self._port_combo.pack(side=tk.LEFT, padx=5)

        tk.Button(
            nav, text="🔄 Refresh", command=self._refresh_ports,
            bg="#9b59b6", fg="white", relief=tk.FLAT, padx=10, pady=6
        ).pack(side=tk.LEFT, padx=5)

        self._btn_connect = tk.Button(
            nav, text="🔌 Connect", command=self._connect_serial,
            bg="#8e44ad", fg="white", relief=tk.FLAT, padx=10, pady=6
        )
        self._btn_connect.pack(side=tk.LEFT, padx=5)

        tk.Button(
            nav, text="⛔ Disconnect", command=self._disconnect_serial,
            bg="#95a5a6", fg="white", relief=tk.FLAT, padx=10, pady=6
        ).pack(side=tk.LEFT, padx=5)

    def _build_views(self) -> None:
        content = tk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.dashboard  = DashboardView(content)
        self.monitoring = MonitoringView(content)
        self.history    = HistoryView(content)

        self._show_main()

    def _start_loops(self) -> None:
        self._update_camera()
        self._monitoring_update()

    # ══════════════════════════════════════════════════════════════════════════
    # View navigation
    # ══════════════════════════════════════════════════════════════════════════

    def _show_main(self) -> None:
        self.monitoring.monitoring_view.pack_forget()
        self.history.history_view.pack_forget()
        self.dashboard.main_view.pack(fill=tk.BOTH, expand=True)

    def _show_monitoring(self) -> None:
        self.dashboard.main_view.pack_forget()
        self.history.history_view.pack_forget()
        self.monitoring.monitoring_view.pack(fill=tk.BOTH, expand=True)

    def _show_history(self) -> None:
        self.dashboard.main_view.pack_forget()
        self.monitoring.monitoring_view.pack_forget()
        self.history.history_view.pack(fill=tk.BOTH, expand=True)
        self.history.pull_data()

    # ══════════════════════════════════════════════════════════════════════════
    # Motor control
    # ══════════════════════════════════════════════════════════════════════════

    def _toggle_motor(self) -> None:
        if not self.motor_running:
            start_motor()
            self._set_motor_running(True)
            self._idle_start = time.monotonic()
        else:
            self._stop_motor(reason="manual")

    def _stop_motor(self, reason: str = "manual") -> None:
        """Stop the conveyor motor and reset idle/detection state.

        Does NOT touch self.processing — the background thread manages
        that flag itself.  Forcing it False here would cause the camera
        loop to accept a new detection while routing is still in flight.
        """
        stop_motor()
        self._set_motor_running(False)
        self._stable_type  = None
        self._stable_start = None
        self._idle_start   = None

        if reason == "idle":
            self.dashboard.status.config(
                text="⏹ Auto-stopped (idle 30 s)", fg="#e74c3c"
            )
            self.dashboard.process_status.config(
                text="No coconut detected for 30 s — motor stopped"
            )
            logger.info("Auto-stop: motor idle for %.0f s", self.IDLE_TIMEOUT)
        else:
            self.dashboard.status.config(text="Motor Stopped", fg="#95a5a6")

    # ══════════════════════════════════════════════════════════════════════════
    # Model loading
    # ══════════════════════════════════════════════════════════════════════════

    def _load_model(self) -> None:
        path = select_model()
        if path:
            filename = path.replace("\\", "/").split("/")[-1]
            self._model_label.config(text=f"Model: {filename}", fg="#27ae60")
        else:
            self._model_label.config(text="No model selected", fg="#e74c3c")

    # ══════════════════════════════════════════════════════════════════════════
    # Serial helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_ports(self) -> None:
        ports = list_serial_ports()
        self._port_combo["values"] = ports
        self._port_var.set(ports[0] if ports else "")

    def _connect_serial(self) -> None:
        port = self._port_var.get()
        if not port:
            self.dashboard.status.config(text="⚠ No port selected", fg="#e74c3c")
            return
        if connect_port(port):
            self.dashboard.status.config(text=f"✓ Connected: {port}", fg="#2ecc71")
        else:
            self.dashboard.status.config(text=f"✗ Failed: {port}", fg="#e74c3c")

    def _disconnect_serial(self) -> None:
        disconnect_port()
        self.dashboard.status.config(text="Disconnected", fg="#95a5a6")

    # ══════════════════════════════════════════════════════════════════════════
    # Camera loop
    # ══════════════════════════════════════════════════════════════════════════

    def _update_camera(self) -> None:
        ret, frame = self.video.read()
        if ret:
            annotated, result, detections = detect_coconut(frame)
            self._handle_detection(result, detections)
            self._push_frame(annotated)

        # Idle auto-stop check
        if self.motor_running and not self.processing and self._idle_start is not None:
            if time.monotonic() - self._idle_start >= self.IDLE_TIMEOUT:
                self._stop_motor(reason="idle")

        self.root.after(self.CAMERA_POLL_MS, self._update_camera)

    def _handle_detection(self, result: str, detections: list[dict]) -> None:
        """
        Update stability timer; trigger processing when threshold is met.

        This runs on the main thread inside _update_camera().
        It only fires the processing pipeline — it does NOT send any
        serial commands itself (those run in the background thread).
        """
        if result != "COCONUT" or not self.motor_running or self.processing:
            self._stable_type  = None
            self._stable_start = None
            return

        maturity   = detections[0]["maturity"]
        confidence = detections[0]["confidence"]
        now        = time.monotonic()

        if self._stable_type != maturity:
            self._stable_type  = maturity
            self._stable_start = now
            return

        elapsed = now - (self._stable_start or now)
        if elapsed < self.STABILITY_THRESHOLD:
            return

        # ── Stable detection confirmed — hand off to background thread ────────
        self.processing        = True
        self._pending_maturity = maturity
        self._pending_conf     = confidence
        self._stable_type      = None
        self._stable_start     = None
        self._idle_start       = None   # suspend idle timer during processing

        # Stop the conveyor on Python side so the button reflects reality.
        # The Arduino also stops itself when its tap ultrasonic fires (COCONUT_DETECTED),
        # but we stop here immediately so the camera can't trigger a second detection.
        self._set_motor_running(False)
        self.dashboard.status.config(
            text="⏸ Coconut detected — processing…", fg="#f39c12"
        )

        threading.Thread(target=self._process_pipeline, daemon=True).start()

    def _push_frame(self, frame: np.ndarray) -> None:
        """Convert BGR frame to Tk image and push to the video label."""
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.dashboard.video_label.configure(image=img)
        self.dashboard.video_label.image = img  # prevent GC

    # ══════════════════════════════════════════════════════════════════════════
    # Single unified background pipeline
    # ══════════════════════════════════════════════════════════════════════════

    def _process_pipeline(self) -> None:
        """
        Full coconut processing pipeline — runs entirely in a background thread.

        Arduino state machine expected sequence
        ----------------------------------------
        Python sends  → Arduino state        → Arduino sends back
        (motor on)      MOTOR_RUNNING          (polling tap ultrasonic)
        (camera sees)   COCONUT_DETECTED       DETECTED  + MOTOR_STOPPED
        TAP           → TAPPING               TAP_DONE
        ROUTE_*       → ROUTING               ROUTED_* or ROUTE_TIMEOUT
        (auto)          COMPLETE → IDLE        ROUTED

        After ROUTED Python sends START_MOTOR → Arduino back to MOTOR_RUNNING.
        """
        def ui(fn): self.root.after(0, fn)

        try:
            # ── Step 1: wait for Arduino tap-ultrasonic confirmation ───────────
            # The Arduino sends DETECTED when the tap sensor fires, then stops
            # the conveyor relay itself (COCONUT_DETECTED state).
            ui(lambda: self.dashboard.process_status.config(
                text="🔍 Waiting for tap-ultrasonic confirmation…"
            ))

            if not wait_for_detection(timeout=self.ULTRASONIC_TIMEOUT):
                logger.warning("Tap ultrasonic timeout — no coconut at tap position")
                ui(lambda: self.dashboard.status.config(
                    text="❌ No coconut at tap sensor — resuming…", fg="#e74c3c"
                ))
                self._restart_motor()
                return

            ui(lambda: self.dashboard.status.config(
                text="✅ Coconut confirmed at tap sensor", fg="#27ae60"
            ))

            # ── Step 2: send TAP command, wait for tap to complete ─────────────
            # Arduino pulse-fires the tap relay (150 ms) then sends TAP_DONE.
            ui(lambda: self.dashboard.process_status.config(
                text="🔨 Tapping coconut…"
            ))
            tap_coconut()

            if not wait_for_tap_done(timeout=self.TAP_DONE_TIMEOUT):
                logger.warning("TAP_DONE timeout — tap relay may have failed")
                ui(lambda: self.dashboard.process_status.config(
                    text="⚠ Tap timeout — resuming motor"
                ))
                self._restart_motor()
                return

            # ── Step 3: record audio immediately after tap ─────────────────────
            # sd.wait() blocks this background thread only, UI stays responsive.
            ui(lambda: self.dashboard.process_status.config(
                text="🔊 Recording tap sound…"
            ))
            tap_type, signal = analyze_tap()
            energy = float(np.mean(np.abs(np.fft.fft(signal)))) if len(signal) else 0.0

            if self.monitoring.is_active() and len(signal):
                ui(lambda: self.monitoring.update_line(signal))

            # ── Step 4: choose final classification ────────────────────────────
            camera_maturity = self._pending_maturity
            if energy >= self.SOUND_ENERGY_MIN:
                final  = tap_type
                method = "Sound ✓"
                ui(lambda: self.dashboard.process_status.config(
                    text=f"🔊 Sound: {tap_type}  (energy {energy:.1f})"
                ))
            else:
                final  = camera_maturity
                method = "Camera fallback"
                ui(lambda: self.dashboard.process_status.config(
                    text=f"⚠ Weak sound ({energy:.1f}) — camera: {camera_maturity}"
                ))
            logger.info("Classification: %s via %s", final, method)
            normalised = _normalize(final)

            # ── Step 5: restart motor so coconut moves toward routing chutes ───
            # This puts the Arduino back into MOTOR_RUNNING state.
            ui(lambda: self.dashboard.status.config(
                text=f"🔄 Conveyor running → routing to {normalised}…", fg="#2ecc71"
            ))
            start_motor()
            self.root.after(0, lambda: self._set_motor_running(True))

            # ── Step 6: send route command ─────────────────────────────────────
            # Arduino enters ROUTING state: polls chute ultrasonic,
            # waits DETECT_DELAY (2 s), fires relay, sends ROUTED_*.
            route_coconut(normalised)
            ui(lambda: self.dashboard.process_status.config(
                text=f"📡 Waiting for {normalised} chute ultrasonic…"
            ))

            if wait_for_routing_complete(timeout=self.ROUTING_TIMEOUT):
                ui(lambda: self.dashboard.process_status.config(
                    text="✓ Coconut routed successfully"
                ))
                logger.info("Routing complete: %s", normalised)
            else:
                ui(lambda: self.dashboard.process_status.config(
                    text="⚠ Routing timeout — continuing anyway"
                ))
                logger.warning("Routing timeout for %s", normalised)

            # ── Step 7: update counters + persist ──────────────────────────────
            if normalised == "MALAUHOG":    self.malauhog_count  += 1
            elif normalised == "MALAKATAD": self.malakatad_count += 1
            elif normalised == "MALAKANIN": self.malakanin_count += 1
            self.total         += 1
            self.coconut_count += 1
            ui(self._update_counters)
            add_record(normalised)

            # ── Step 8: short pause then signal ready for next coconut ─────────
            drain_serial()
            time.sleep(self.POST_ROUTE_DELAY)

            ui(lambda: self.dashboard.process_status.config(
                text="✅ Ready — waiting for next coconut…"
            ))
            logger.info("Cycle complete — motor running, waiting for next coconut")

        except Exception as exc:
            logger.error("_process_pipeline: %s", exc)
            ui(lambda: self.dashboard.status.config(
                text="⚠ Pipeline error — resuming motor", fg="#e74c3c"
            ))
            self._restart_motor()

        finally:
            # Always clear the processing flag and reset the idle timer.
            # Done last so the camera loop cannot start a new detection
            # until this entire cycle is fully wound down.
            self.processing        = False
            self._pending_maturity = None
            self._pending_conf     = 0.0
            self.root.after(0, self._reset_idle_timer)

    def _restart_motor(self) -> None:
        """
        Send START_MOTOR to Arduino and update Python state.

        Called from the background thread on any early-exit path.
        All UI writes are dispatched to the main thread via root.after().
        """
        start_motor()   # puts Arduino back into MOTOR_RUNNING state
        self.root.after(0, lambda: self._set_motor_running(True))
        self.root.after(0, self._reset_idle_timer)

    def _set_motor_running(self, running: bool) -> None:
        """Set motor_running and sync the button label — main thread only."""
        self.motor_running = running
        if running:
            self._btn_motor.config(text="⏹ STOP MOTOR", bg="#e74c3c")
            self.dashboard.status.config(text="🔄 Motor Running", fg="#2ecc71")
        else:
            self._btn_motor.config(text="▶ START MOTOR", bg="#2ecc71")

    def _reset_idle_timer(self) -> None:
        """(Re)start the idle countdown — main thread only."""
        if self.motor_running:
            self._idle_start = time.monotonic()

    # ══════════════════════════════════════════════════════════════════════════
    # Counter display
    # ══════════════════════════════════════════════════════════════════════════

    def _update_counters(self) -> None:
        self.dashboard.counter.config(
            text=f"Total: {self.total}\nCoconuts: {self.coconut_count}"
        )
        self.dashboard.type_label.config(
            text=(
                f"Malakanin: {self.malauhog_count}\n"
                f"Malakatad: {self.malakatad_count}\n"
                f"Malauhog: {self.malakanin_count}"
            )
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Audio monitoring loop
    # ══════════════════════════════════════════════════════════════════════════

    def _monitoring_update(self) -> None:
        if self.monitoring.is_active():
            try:
                chunk = sd.rec(
                    int(0.1 * 44_100), samplerate=44_100, channels=1, dtype="float32"
                )
                # NOTE: no sd.wait() here — we don't block the UI thread.
                # The chunk from the previous call (buffered by sounddevice) is
                # typically ready; if not, we simply skip this tick.
                if chunk is not None and len(chunk):
                    self._audio_buf.extend(chunk[:, 0])
                    if len(self._audio_buf) > 100:
                        self.monitoring.update_line(np.array(list(self._audio_buf)))
            except Exception as exc:
                logger.debug("monitoring_update: %s", exc)

        self.root.after(self.MONITOR_POLL_MS, self._monitoring_update)

    # ══════════════════════════════════════════════════════════════════════════
    # Shutdown
    # ══════════════════════════════════════════════════════════════════════════

    def on_close(self) -> None:
        try:
            send("CLOSE")
        except Exception:
            pass
        self.video.release()
        self.root.destroy()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = CoconutSorter(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()