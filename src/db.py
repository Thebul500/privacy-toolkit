"""SQLite database layer for Privacy Toolkit."""

from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from src.config import TOOLKIT_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    scanner TEXT NOT NULL,
    scan_type TEXT NOT NULL,
    query TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT DEFAULT 'running',
    result_count INTEGER DEFAULT 0,
    raw_output_path TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id INTEGER NOT NULL,
    profile TEXT NOT NULL,
    source TEXT NOT NULL,
    site_name TEXT NOT NULL,
    site_url TEXT,
    data_type TEXT,
    details TEXT,
    confidence TEXT DEFAULT 'medium',
    found_at TEXT NOT NULL,
    FOREIGN KEY (scan_id) REFERENCES scans(id)
);

CREATE TABLE IF NOT EXISTS removal_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    broker_slug TEXT NOT NULL,
    broker_name TEXT NOT NULL,
    method TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    submitted_at TEXT,
    confirmed_at TEXT,
    recheck_at TEXT,
    next_rescan_at TEXT,
    email_message_id TEXT,
    screenshot_path TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    profile TEXT,
    details TEXT,
    success INTEGER DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_findings_profile ON findings(profile);
CREATE INDEX IF NOT EXISTS idx_findings_site ON findings(site_name);
CREATE INDEX IF NOT EXISTS idx_removal_status ON removal_requests(status);
CREATE INDEX IF NOT EXISTS idx_removal_profile ON removal_requests(profile);
CREATE INDEX IF NOT EXISTS idx_scans_profile ON scans(profile);
"""


class Database:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = "data/privacy_toolkit.db"
        full_path = TOOLKIT_DIR / db_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = str(full_path)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        conn.close()

    # --- Scans ---

    def create_scan(self, profile: str, scanner: str, scan_type: str, query: str) -> int:
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO scans (profile, scanner, scan_type, query, started_at) VALUES (?, ?, ?, ?, ?)",
            (profile, scanner, scan_type, query, _now()),
        )
        scan_id = cur.lastrowid
        conn.commit()
        conn.close()
        self.log("scan_started", profile, {"scanner": scanner, "query": query})
        return scan_id

    def complete_scan(self, scan_id: int, result_count: int, output_path: str = "") -> None:
        conn = self._connect()
        conn.execute(
            "UPDATE scans SET status='completed', completed_at=?, result_count=?, raw_output_path=? WHERE id=?",
            (_now(), result_count, output_path, scan_id),
        )
        conn.commit()
        conn.close()

    def fail_scan(self, scan_id: int, error: str) -> None:
        conn = self._connect()
        conn.execute(
            "UPDATE scans SET status='failed', completed_at=?, error_message=? WHERE id=?",
            (_now(), error, scan_id),
        )
        conn.commit()
        conn.close()

    def get_scans(self, profile: Optional[str] = None, limit: int = 50) -> list[dict]:
        conn = self._connect()
        if profile:
            rows = conn.execute(
                "SELECT * FROM scans WHERE profile=? ORDER BY id DESC LIMIT ?",
                (profile, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scans ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # --- Findings ---

    def add_finding(
        self,
        scan_id: int,
        profile: str,
        source: str,
        site_name: str,
        site_url: str = "",
        data_type: str = "",
        details: Optional[dict] = None,
        confidence: str = "medium",
    ) -> int:
        conn = self._connect()
        cur = conn.execute(
            """INSERT INTO findings
            (scan_id, profile, source, site_name, site_url, data_type, details, confidence, found_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, profile, source, site_name, site_url, data_type,
             json.dumps(details or {}), confidence, _now()),
        )
        fid = cur.lastrowid
        conn.commit()
        conn.close()
        return fid

    def get_findings(self, profile: Optional[str] = None, source: Optional[str] = None) -> list[dict]:
        conn = self._connect()
        query = "SELECT * FROM findings WHERE 1=1"
        params: list[Any] = []
        if profile:
            query += " AND profile=?"
            params.append(profile)
        if source:
            query += " AND source=?"
            params.append(source)
        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("details"):
                try:
                    d["details"] = json.loads(d["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def get_findings_for_broker(self, profile: str, broker_slug: str) -> list[dict]:
        """Get findings matching a specific broker slug for a profile."""
        conn = self._connect()
        rows = conn.execute(
            """SELECT * FROM findings
            WHERE profile=? AND (
                site_name LIKE ? OR
                details LIKE ?
            )
            ORDER BY id DESC""",
            (profile, f"%{broker_slug}%", f"%{broker_slug}%"),
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("details"):
                try:
                    d["details"] = json.loads(d["details"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results

    def get_findings_count(self, profile: Optional[str] = None) -> int:
        conn = self._connect()
        if profile:
            row = conn.execute("SELECT COUNT(*) FROM findings WHERE profile=?", (profile,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM findings").fetchone()
        conn.close()
        return row[0]

    # --- Removal Requests ---

    def create_removal(
        self,
        profile: str,
        broker_slug: str,
        broker_name: str,
        method: str,
        recheck_days: int = 30,
        rescan_days: int = 90,
    ) -> int:
        now = _now()
        conn = self._connect()
        cur = conn.execute(
            """INSERT INTO removal_requests
            (profile, broker_slug, broker_name, method, status, created_at, updated_at, recheck_at, next_rescan_at)
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
            (profile, broker_slug, broker_name, method, now, now,
             _future(recheck_days), _future(rescan_days)),
        )
        rid = cur.lastrowid
        conn.commit()
        conn.close()
        return rid

    def update_removal_status(self, removal_id: int, status: str, **kwargs: Any) -> None:
        conn = self._connect()
        sets = ["status=?", "updated_at=?"]
        params: list[Any] = [status, _now()]
        if status == "submitted":
            sets.append("submitted_at=?")
            params.append(_now())
        if status == "confirmed":
            sets.append("confirmed_at=?")
            params.append(_now())
        for key in ("email_message_id", "screenshot_path", "notes"):
            if key in kwargs:
                sets.append(f"{key}=?")
                params.append(kwargs[key])
        params.append(removal_id)
        conn.execute(f"UPDATE removal_requests SET {', '.join(sets)} WHERE id=?", params)
        conn.commit()
        conn.close()

    def get_removals(
        self,
        profile: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        conn = self._connect()
        query = "SELECT * FROM removal_requests WHERE 1=1"
        params: list[Any] = []
        if profile:
            query += " AND profile=?"
            params.append(profile)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_overdue_removals(self, days: int = 45) -> list[dict]:
        """Get submitted removals older than N days with no confirmation (need follow-up)."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = self._connect()
        rows = conn.execute(
            """SELECT * FROM removal_requests
            WHERE status='submitted' AND submitted_at <= ?
            AND notes NOT LIKE '%follow_up_sent%'
            ORDER BY submitted_at ASC""",
            (cutoff,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_pending_rechecks(self, profile: Optional[str] = None) -> list[dict]:
        conn = self._connect()
        query = "SELECT * FROM removal_requests WHERE status='submitted' AND recheck_at <= ?"
        params: list[Any] = [_now()]
        if profile:
            query += " AND profile=?"
            params.append(profile)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # --- Audit Log ---

    def log(self, action: str, profile: Optional[str] = None,
            details: Optional[dict] = None, success: bool = True) -> None:
        conn = self._connect()
        conn.execute(
            "INSERT INTO audit_log (timestamp, action, profile, details, success) VALUES (?, ?, ?, ?, ?)",
            (_now(), action, profile, json.dumps(details or {}), int(success)),
        )
        conn.commit()
        conn.close()

    def get_audit_log(self, limit: int = 100) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


def _now() -> str:
    return datetime.now().isoformat()


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()
