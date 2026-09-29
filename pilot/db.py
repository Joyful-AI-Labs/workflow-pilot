"""SQLite state: one row per invoice, plus an event log. Stdlib only."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  file TEXT NOT NULL,
  status TEXT NOT NULL,            -- queued | extracting | matching | matched | review | rejected | approved | error
  invoice_json TEXT,
  match_json TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  invoice_id INTEGER,
  level TEXT NOT NULL,
  message TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path = config.DB_PATH) -> sqlite3.Connection:
    global _conn
    if _conn is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(path, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def reset() -> None:
    with _lock:
        c = connect()
        c.executescript("DELETE FROM invoices; DELETE FROM events; DELETE FROM sqlite_sequence;")
        c.commit()


def add_invoice(file: str) -> int:
    with _lock:
        c = connect()
        cur = c.execute("INSERT INTO invoices (file, status, created, updated) VALUES (?, 'queued', ?, ?)", (file, _now(), _now()))
        c.commit()
        return cur.lastrowid


def set_status(invoice_id: int, status: str, invoice=None, result=None) -> None:
    with _lock:
        c = connect()
        sets, vals = ["status = ?", "updated = ?"], [status, _now()]
        if invoice is not None:
            sets.append("invoice_json = ?"); vals.append(invoice.model_dump_json())
        if result is not None:
            sets.append("match_json = ?"); vals.append(result.model_dump_json())
        vals.append(invoice_id)
        c.execute(f"UPDATE invoices SET {', '.join(sets)} WHERE id = ?", vals)
        c.commit()


def log(message: str, invoice_id: int | None = None, level: str = "info") -> None:
    with _lock:
        c = connect()
        c.execute("INSERT INTO events (ts, invoice_id, level, message) VALUES (?, ?, ?, ?)", (_now(), invoice_id, level, message))
        c.commit()


def get_invoice(invoice_id: int) -> dict | None:
    row = connect().execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return _row(row) if row else None


def known_files() -> set[str]:
    return {r["file"] for r in connect().execute("SELECT file FROM invoices")}


def state(limit_events: int = 200) -> dict:
    c = connect()
    invoices = [_row(r) for r in c.execute("SELECT * FROM invoices ORDER BY id")]
    events = [dict(r) for r in c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit_events,))][::-1]
    return {"invoices": invoices, "events": events}


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["invoice"] = json.loads(d.pop("invoice_json") or "null")
    d["match"] = json.loads(d.pop("match_json") or "null")
    return d
