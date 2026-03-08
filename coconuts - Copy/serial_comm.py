# serial_comm.py
"""
Serial communication layer for the Coconut Sorting System.

All Arduino I/O goes through this module.  The connection is intentionally
left uninitialized at import time so that the UI can let the user pick a
port before anything is sent.
"""

import logging
import time

import serial
import serial.tools.list_ports

logger = logging.getLogger(__name__)

# ── module-level state ────────────────────────────────────────────────────────
_arduino: serial.Serial | None = None
_BAUD    = 9_600
_TIMEOUT = 0.1   # seconds for readline
# ─────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════
# Connection management
# ══════════════════════════════════════════════

def init_serial() -> None:
    """No-op placeholder – connection is handled by the UI."""
    global _arduino
    _arduino = None


def list_serial_ports() -> list[str]:
    """Return device names for every detected serial port (e.g. ['COM3', '/dev/ttyUSB0'])."""
    try:
        return [p.device for p in serial.tools.list_ports.comports()]
    except Exception as exc:
        logger.error("list_serial_ports: %s", exc)
        return []


def connect_port(port: str, baud: int = _BAUD, timeout: float = _TIMEOUT) -> bool:
    """
    Open *port* and store the connection.

    Returns True on success.
    """
    global _arduino
    if not port:
        return False
    try:
        _arduino = serial.Serial(port, baud, timeout=timeout)
        time.sleep(2)          # Allow Arduino to reset after DTR toggle
        logger.info("Connected to Arduino on %s", port)
        return True
    except serial.SerialException as exc:
        logger.error("connect_port(%s): %s", port, exc)
        _arduino = None
        return False


def disconnect_port() -> None:
    """Close the current serial connection."""
    global _arduino
    try:
        if _arduino and _arduino.is_open:
            _arduino.close()
            logger.info("Arduino disconnected")
    except Exception as exc:
        logger.error("disconnect_port: %s", exc)
    finally:
        _arduino = None


def is_connected() -> bool:
    """Return True if a serial port is currently open."""
    return _arduino is not None and _arduino.is_open


# ══════════════════════════════════════════════
# Low-level I/O
# ══════════════════════════════════════════════

def send(cmd: str) -> bool:
    """
    Write a newline-terminated command to the Arduino.

    Returns True if the write succeeded, False if the port is unavailable.
    """
    if not is_connected():
        logger.warning("send('%s'): no serial connection", cmd)
        return False
    try:
        _arduino.write((cmd + "\n").encode())
        logger.debug("→ %s", cmd)
        return True
    except serial.SerialException as exc:
        logger.error("send error: %s", exc)
        return False


def read_sensor() -> str:
    """
    Return one line from the Arduino (stripped), or '' if nothing waiting.
    """
    if not is_connected():
        return ""
    try:
        if _arduino.in_waiting > 0:
            line = _arduino.readline().decode(errors="replace").strip()
            if line:
                logger.debug("← %s", line)
            return line
    except serial.SerialException as exc:
        logger.error("read_sensor error: %s", exc)
    return ""


def drain_serial() -> None:
    """
    Discard any pending bytes in the receive buffer.

    Call after each coconut cycle to prevent stale messages from
    interfering with the next iteration.
    """
    if not is_connected():
        return
    try:
        while _arduino.in_waiting > 0:
            msg = _arduino.readline().decode(errors="replace").strip()
            if msg:
                logger.debug("[drained] %s", msg)
    except Exception as exc:
        logger.error("drain_serial: %s", exc)


# ══════════════════════════════════════════════
# High-level Arduino commands
# ══════════════════════════════════════════════

def start_motor()  -> None: send("START_MOTOR")
def stop_motor()   -> None: send("STOP_MOTOR")
def tap_coconut()  -> None: send("TAP")


_ROUTE_COMMANDS = {
    "Mature":    "ROUTE_MALAUHOG",
    "MALAUHOG":  "ROUTE_MALAUHOG",
    "Potential": "ROUTE_MALAKATAD",
    "MALAKATAD": "ROUTE_MALAKATAD",
    "Premature": "ROUTE_MALAKANIN",
    "MALAKANIN": "ROUTE_MALAKANIN",
}

def route_coconut(maturity_type: str) -> bool:
    """
    Send the appropriate ROUTE_* command for *maturity_type*.

    Accepts both camera maturity strings ('Mature' / 'Potential' / 'Premature')
    and the normalised Tagalog labels ('MALAUHOG' / 'MALAKATAD' / 'MALAKANIN').

    The Arduino will:
      1. Enter ROUTING state.
      2. Poll the ultrasonic sensor at the designated chute (≤ 5 s).
      3. Activate the relay only when coconut presence is confirmed.
      4. Reply with ROUTED_* or ROUTE_TIMEOUT.

    Returns True if the command was sent, False otherwise.
    """
    cmd = _ROUTE_COMMANDS.get(maturity_type)
    if cmd is None:
        logger.error("route_coconut: unknown type '%s'", maturity_type)
        return False
    return send(cmd)


# ══════════════════════════════════════════════
# Blocking wait helpers (run in background threads)
# ══════════════════════════════════════════════

def _wait_for(keywords: list[str], timeout: float, poll: float = 0.05) -> bool:
    """
    Poll read_sensor() until a response containing any *keyword* arrives
    or *timeout* seconds elapse.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = read_sensor()
        if any(kw in response for kw in keywords):
            return True
        time.sleep(poll)
    return False


def wait_for_detection(timeout: float = 10.0) -> bool:
    """Block until the Arduino sends 'DETECTED' or *timeout* expires."""
    return _wait_for(["DETECTED"], timeout)


def wait_for_tap_done(timeout: float = 3.0) -> bool:
    """Block until the Arduino sends 'TAP_DONE' or *timeout* expires."""
    return _wait_for(["TAP_DONE"], timeout)


def wait_for_motor_stopped(timeout: float = 2.0) -> bool:
    """Block until the Arduino sends 'MOTOR_STOPPED' or *timeout* expires."""
    return _wait_for(["MOTOR_STOPPED"], timeout)


def wait_for_routing_complete(timeout: float = 10.0) -> bool:
    """
    Block until the Arduino confirms routing or times out.

    Accepts: ROUTED_*, ROUTE_TIMEOUT, MOTOR_RESUMED
    """
    return _wait_for(["ROUTED", "ROUTE_TIMEOUT", "MOTOR_RESUMED"], timeout)