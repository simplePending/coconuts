# data_manager.py
"""
Persistent data storage for the Coconut Sorting System.
Uses SQLite for reliable, concurrent-safe, production-grade storage.
"""

import sqlite3
import os
import csv
import logging
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_FILE = "coconut_data.db"
VALID_TYPES = {"MALAUHOG", "MALAKATAD", "MALAKANIN"}


# ──────────────────────────────────────────────
# Database initialisation
# ──────────────────────────────────────────────

def init_db():
    """Create tables if they do not exist. Call once at startup."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                date      TEXT    NOT NULL,
                time      TEXT    NOT NULL,
                type      TEXT    NOT NULL CHECK(type IN ('MALAUHOG','MALAKATAD','MALAKANIN')),
                timestamp TEXT    NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_date ON records(date)")
    logger.info("Database initialised: %s", DB_FILE)


@contextmanager
def _get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ──────────────────────────────────────────────
# Write
# ──────────────────────────────────────────────

def add_record(tap_type: str) -> dict | None:
    """
    Persist a single coconut-sorting result.

    Parameters
    ----------
    tap_type : str
        One of 'MALAUHOG', 'MALAKATAD', 'MALAKANIN'.

    Returns
    -------
    dict with the saved record, or None on failure.
    """
    if tap_type not in VALID_TYPES:
        logger.error("add_record: invalid type '%s'", tap_type)
        return None

    now = datetime.now()
    record = {
        "date":      now.strftime("%Y-%m-%d"),
        "time":      now.strftime("%H:%M"),
        "type":      tap_type,
        "timestamp": now.isoformat(),
    }
    try:
        with _get_conn() as conn:
            conn.execute(
                "INSERT INTO records (date, time, type, timestamp) VALUES (?,?,?,?)",
                (record["date"], record["time"], record["type"], record["timestamp"]),
            )
        logger.debug("Record saved: %s", record)
        return record
    except Exception as exc:
        logger.error("Failed to save record: %s", exc)
        return None


# ──────────────────────────────────────────────
# Read
# ──────────────────────────────────────────────

def get_data_by_date_range(start_date, end_date) -> list[dict]:
    """
    Return all records whose date falls within [start_date, end_date].

    Parameters
    ----------
    start_date, end_date : datetime.date
    """
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT date, time, type, timestamp FROM records "
                "WHERE date BETWEEN ? AND ? ORDER BY timestamp",
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.error("get_data_by_date_range error: %s", exc)
        return []


def aggregate_by_date(records: list[dict]) -> dict:
    """
    Aggregate a list of records into per-date counts.

    Returns
    -------
    {
        "2025-01-01": {"Malauhog": 3, "Malakatad": 1, "Malakanin": 2},
        ...
    }
    """
    aggregated: dict[str, dict[str, int]] = {}
    for record in records:
        date = record["date"]
        rtype = record["type"]
        if date not in aggregated:
            aggregated[date] = {"Malauhog": 0, "Malakatad": 0, "Malakanin": 0}
        # Normalise stored keys (DB stores upper-case labels)
        label_map = {
            "MALAUHOG":  "Malauhog",
            "MALAKATAD": "Malakatad",
            "MALAKANIN": "Malakanin",
        }
        display_key = label_map.get(rtype)
        if display_key:
            aggregated[date][display_key] += 1
    return aggregated


# ──────────────────────────────────────────────
# Export
# ──────────────────────────────────────────────

def export_to_csv(records: list[dict], filename: str = "coconut_data.csv") -> bool:
    """
    Write records to a CSV file.

    Returns True on success, False on failure.
    """
    if not records:
        logger.warning("export_to_csv: no records to export")
        return False
    try:
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "time", "type", "timestamp"])
            writer.writeheader()
            writer.writerows(records)
        logger.info("Exported %d records to %s", len(records), filename)
        return True
    except Exception as exc:
        logger.error("export_to_csv error: %s", exc)
        return False


# ──────────────────────────────────────────────
# Initialise on import
# ──────────────────────────────────────────────
init_db()