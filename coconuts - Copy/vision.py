# vision.py
"""
YOLO-based coconut detection for the Coconut Sorting System.

Usage
-----
1. Call select_model() to let the user choose a .pt weights file.
2. Pass camera frames to detect_coconut() to get annotated results.
"""

import logging
import os

import cv2
import numpy as np
import torch
from tkinter import filedialog
import tkinter as tk
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# ── module-level state ────────────────────────────────────────────────────────
_model: YOLO | None = None
_model_path: str | None = None
_device: str = "cpu"
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_device() -> str:
    """Return 'cuda' if a CUDA-capable GPU is available, else 'cpu'."""
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        logger.info("GPU available: %s  (CUDA %s)", name, torch.version.cuda)
        return "cuda"
    logger.warning("No GPU found — running inference on CPU")
    return "cpu"


# Resolve device once at import time
_device = _resolve_device()


# ══════════════════════════════════════════════
# Model management
# ══════════════════════════════════════════════

def select_model() -> str | None:
    """
    Open a file-picker dialog and load the chosen YOLO weights.

    Returns the selected file path, or None if cancelled.
    """
    global _model, _model_path

    root = tk.Tk()
    root.withdraw()
    path = filedialog.askopenfilename(
        title="Select YOLO Model Weights (.pt)",
        filetypes=[("YOLO weights", "*.pt"), ("All files", "*.*")],
        initialdir=os.path.expanduser("~"),
    )
    root.destroy()

    if not path:
        logger.info("Model selection cancelled")
        return None

    _model_path = path
    _model = None        # Force reload on next detect_coconut() call
    logger.info("Model path set: %s", path)
    return path


def _load_model() -> YOLO | None:
    """
    (Re-)load the YOLO model from *_model_path*.

    Returns the loaded model or None on failure.
    """
    global _model

    if _model is not None:
        return _model

    if not _model_path:
        logger.error("No model path set. Call select_model() first.")
        return None

    if not os.path.isfile(_model_path):
        logger.error("Model file not found: %s", _model_path)
        return None

    try:
        _model = YOLO(_model_path)
        _model.to(_device)
        logger.info("YOLO model loaded on %s: %s", _device.upper(), _model_path)
    except Exception as exc:
        logger.error("Failed to load YOLO model: %s", exc)
        _model = None

    return _model


# ══════════════════════════════════════════════
# Inference
# ══════════════════════════════════════════════

def detect_coconut(
    frame: np.ndarray,
    conf_threshold: float = 0.35,
) -> tuple[np.ndarray, str, list[dict]]:
    """
    Run YOLO inference on *frame* and return detection results.

    Parameters
    ----------
    frame : np.ndarray
        BGR image from OpenCV.
    conf_threshold : float
        Minimum confidence to accept a detection.

    Returns
    -------
    annotated_frame : np.ndarray
        Frame with bounding boxes drawn by YOLO.
    status : str
        'COCONUT' if at least one object was detected, 'NONE' otherwise.
    detections : list[dict]
        Each dict contains:
          - class (int)       : class index
          - maturity (str)    : class name from the model
          - confidence (float): detection confidence [0, 1]
          - bbox (tuple)      : (x1, y1, x2, y2) in pixels
    """
    model = _load_model()
    if model is None:
        return frame, "NONE", []

    try:
        results = model.predict(frame, conf=conf_threshold, device=_device, verbose=False)
        annotated_frame = results[0].plot()
        boxes = results[0].boxes

        if len(boxes) == 0:
            return annotated_frame, "NONE", []

        detections = []
        for box in boxes:
            x1, y1, x2, y2 = box.xyxy[0].int().tolist()
            detections.append({
                "class":      int(box.cls[0].item()),
                "maturity":   model.names[int(box.cls[0].item())],
                "confidence": float(box.conf[0].item()),
                "bbox":       (x1, y1, x2, y2),
            })

        return annotated_frame, "COCONUT", detections

    except Exception as exc:
        logger.error("detect_coconut error: %s", exc)
        return frame, "NONE", []