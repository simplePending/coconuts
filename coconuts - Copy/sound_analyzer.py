# sound_analyzer.py
"""
Tap-sound analyser for the Coconut Sorting System.

Records a short audio burst after the tap relay fires, then uses
FFT energy to classify coconut maturity.

Classification thresholds should be calibrated against real samples;
the defaults here are starting points.
"""

import logging

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

# ── tuneable constants ────────────────────────────────────────────────────────
SAMPLE_RATE   = 44_100      # Hz
DURATION      = 0.4         # seconds – enough to capture the tap transient
CHANNELS      = 1
DEVICE        = None        # None → system default; set to device index if needed

# Energy thresholds (mean |FFT| of the full signal)
THRESHOLD_MALAUHOG  = 15.0  # above this  → hard/mature
THRESHOLD_MALAKATAD = 10.0  # above this  → medium
# below MALAKATAD → soft/young (MALAKANIN)
# ─────────────────────────────────────────────────────────────────────────────


def analyze_tap() -> tuple[str, np.ndarray]:
    """
    Record audio from the microphone and classify coconut maturity.

    Returns
    -------
    tap_type : str
        One of 'MALAUHOG', 'MALAKATAD', 'MALAKANIN'.
    signal : np.ndarray, shape (N,)
        Mono audio samples (float32).  Empty array on capture failure.
    """
    try:
        audio = sd.rec(
            int(SAMPLE_RATE * DURATION),
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            device=DEVICE,
        )
        sd.wait()

        signal: np.ndarray = audio[:, 0]

        energy = float(np.mean(np.abs(np.fft.fft(signal))))
        tap_type = _classify(energy)

        logger.debug("analyze_tap → type=%s  energy=%.3f", tap_type, energy)
        return tap_type, signal

    except sd.PortAudioError as exc:
        logger.error("Audio capture error (PortAudio): %s", exc)
    except Exception as exc:
        logger.error("Audio capture error: %s", exc)

    # Safe fallback: treat as softest class so the system keeps moving
    return "MALAKANIN", np.array([], dtype="float32")


def _classify(energy: float) -> str:
    """Map FFT energy to a maturity label."""
    if energy > THRESHOLD_MALAUHOG:
        return "MALAUHOG"
    if energy > THRESHOLD_MALAKATAD:
        return "MALAKATAD"
    return "MALAKANIN"