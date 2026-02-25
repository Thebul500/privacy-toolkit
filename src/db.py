"""SQLite database layer for Privacy Toolkit."""

from __future__ import annotations
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)

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

CREATE TABLE IF NOT EXISTS score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile TEXT NOT NULL,
    score INTEGER NOT NULL,
    grade TEXT NOT NULL,
    details TEXT DEFAULT '{}',
    calculated_at TEXT DEFAULT (datetime('now'))
);
"""


VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"submitted", "pending_captcha"},
    "submitted": {"confirmed", "rejected", "submitted"},
    "confirmed": {"reappeared"},
    "rejected": {"pending", "submitted"},
    "reappeared": {"pending", "submitted"},
    "pending_captcha": {"pending", "submitted"},
}


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
        try:
            conn = self._connect()
            conn.executescript(SCHEMA)
            # One-time dedup cleanup: keep lowest-ID row per unique group,
            # then create unique index (must dedup before index creation)
            conn.execute("""
                DELETE FROM findings WHERE id NOT IN (
                    SELECT MIN(id) FROM findings
                    GROUP BY profile, source, site_name, site_url, data_type
                )
            """)
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_findings_unique
                ON findings(profile, source, site_name, site_url, data_type)
            """)
            # Phase 1 migration: rescan_count column
            try:
                conn.execute("ALTER TABLE removal_requests ADD COLUMN rescan_count INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            logger.error("Failed to initialize database schema at %s: %s", self.path, e)
            raise

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
            """INSERT OR IGNORE INTO findings
            (scan_id, profile, source, site_name, site_url, data_type, details, confidence, found_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, profile, source, site_name, site_url, data_type,
             json.dumps(details or {}), confidence, _now()),
        )
        fid = cur.lastrowid
        if fid == 0 or cur.rowcount == 0:
            # Row already exists — fetch its ID
            row = conn.execute(
                """SELECT id FROM findings
                WHERE profile=? AND source=? AND site_name=? AND site_url=? AND data_type=?""",
                (profile, source, site_name, site_url, data_type),
            ).fetchone()
            fid = row["id"] if row else 0
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
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to parse finding details JSON for finding_id=%s: %s", d.get("id"), e)
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
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning("Failed to parse finding details JSON for finding_id=%s broker=%s: %s", d.get("id"), broker_slug, e)
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
        row = conn.execute(
            "SELECT status FROM removal_requests WHERE id=?", (removal_id,)
        ).fetchone()
        if row is None:
            conn.close()
            raise ValueError(f"Removal request {removal_id} not found")
        current = row["status"]
        allowed = VALID_TRANSITIONS.get(current, set())
        if status not in allowed:
            conn.close()
            raise ValueError(
                f"Invalid status transition: {current} -> {status} "
                f"(allowed: {sorted(allowed)})"
            )
        ALLOWED_COLUMNS = frozenset({
            "status", "updated_at", "submitted_at", "confirmed_at",
            "email_message_id", "screenshot_path", "notes",
        })
        updates: dict[str, Any] = {"status": status, "updated_at": _now()}
        if status == "submitted":
            updates["submitted_at"] = _now()
        if status == "confirmed":
            updates["confirmed_at"] = _now()
        for key in ("email_message_id", "screenshot_path", "notes"):
            if key in kwargs:
                if key not in ALLOWED_COLUMNS:
                    raise ValueError(f"Disallowed column: {key}")
                updates[key] = kwargs[key]
        cols = list(updates.keys())
        params = [updates[c] for c in cols]
        params.append(removal_id)
        set_clause = ", ".join(f"{c}=?" for c in cols)
        # nosemgrep: sqlalchemy-execute-raw-query — cols from ALLOWED_COLUMNS whitelist, values use ? params
        conn.execute(
            "UPDATE removal_requests SET " + set_clause + " WHERE id=?",  # nosec B608
            params,
        )
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

    def get_overdue_removals(
        self,
        profile: Optional[str] = None,
        days_threshold: Optional[int] = None,
    ) -> list[dict]:
        """Get submitted removals that are overdue and eligible for follow-up.

        A removal is overdue when:
          - status = 'submitted'
          - submitted_at + recheck_days < current date (uses days_threshold
            override if provided, otherwise falls back to the recheck_at column
            which was set from broker.verification.expected_days)
          - no 'follow_up_sent' note within the last 30 days

        Args:
            profile: Filter by profile name (optional).
            days_threshold: Override the per-broker expected_days with a flat
                            threshold in days.  When provided, a removal is
                            overdue if submitted_at + days_threshold < now.
        """
        conn = self._connect()

        if days_threshold is not None:
            # Flat cutoff: submitted more than days_threshold days ago
            cutoff = (datetime.now() - timedelta(days=days_threshold)).isoformat()
            query = """SELECT * FROM removal_requests
                WHERE status='submitted'
                AND submitted_at <= ?"""
            params: list[Any] = [cutoff]
        else:
            # Per-broker cutoff: recheck_at is set to submitted_at + expected_days
            # at creation time.  Overdue when recheck_at <= now.
            query = """SELECT * FROM removal_requests
                WHERE status='submitted'
                AND recheck_at <= ?"""
            params = [datetime.now().isoformat()]

        if profile:
            query += " AND profile=?"
            params.append(profile)

        query += " ORDER BY submitted_at ASC"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        # Post-filter: exclude removals where a follow-up was already sent
        # within the last 30 days.
        results = []
        recent_cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        for row in rows:
            d = dict(row)
            notes = d.get("notes") or ""
            # Check if any follow_up_sent:<date> entry is within last 30 days
            skip = False
            for part in notes.split(";"):
                part = part.strip()
                if part.startswith("follow_up_sent:"):
                    sent_date = part.split(":", 1)[1].strip()
                    if sent_date >= recent_cutoff:
                        skip = True
                        break
            if not skip:
                results.append(d)

        return results

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

    # --- Score History ---

    def save_score(self, profile: str, score: int, grade: str, details: Optional[dict] = None) -> int:
        conn = self._connect()
        cur = conn.execute(
            "INSERT INTO score_history (profile, score, grade, details, calculated_at) VALUES (?, ?, ?, ?, ?)",
            (profile, score, grade, json.dumps(details or {}), _now()),
        )
        sid = cur.lastrowid
        conn.commit()
        conn.close()
        return sid

    def get_score_history(self, profile: str, limit: int = 90) -> list[dict]:
        conn = self._connect()
        rows = conn.execute(
            "SELECT * FROM score_history WHERE profile=? ORDER BY id DESC LIMIT ?",
            (profile, limit),
        ).fetchall()
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

    # --- Broker Compliance ---

    def get_broker_compliance(self, broker_slug: Optional[str] = None) -> list[dict]:
        """Compute per-broker compliance stats from removal request data."""
        conn = self._connect()
        query = """
            SELECT
                broker_slug,
                broker_name,
                COUNT(*) AS total_requests,
                SUM(CASE WHEN confirmed_at IS NOT NULL THEN 1 ELSE 0 END) AS confirmed_count,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected_count,
                SUM(CASE WHEN status = 'reappeared' THEN 1 ELSE 0 END) AS reappeared_count,
                SUM(CASE WHEN notes LIKE '%bounce%' THEN 1 ELSE 0 END) AS bounce_count,
                AVG(CASE WHEN confirmed_at IS NOT NULL
                    THEN julianday(confirmed_at) - julianday(submitted_at)
                    ELSE NULL END) AS avg_days_to_confirm
            FROM removal_requests
        """
        params: list[Any] = []
        if broker_slug:
            query += " WHERE broker_slug = ?"
            params.append(broker_slug)
        query += " GROUP BY broker_slug ORDER BY total_requests DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()

        results = []
        for r in rows:
            d = dict(r)
            total = d["total_requests"]
            confirmed = d["confirmed_count"]
            reappeared = d["reappeared_count"]

            d["compliance_rate"] = round((confirmed / total) * 100, 1) if total > 0 else 0.0
            d["reappearance_rate"] = round((reappeared / total) * 100, 1) if total > 0 else 0.0
            d["avg_days_to_confirm"] = round(d["avg_days_to_confirm"], 1) if d["avg_days_to_confirm"] else None

            if total < 3:
                d["compliance_label"] = "undetermined"
            elif d["compliance_rate"] > 80:
                d["compliance_label"] = "compliant"
            elif d["compliance_rate"] >= 50:
                d["compliance_label"] = "inconsistent"
            else:
                d["compliance_label"] = "resistant"

            results.append(d)
        return results

    # --- Confirmed Rescan ---

    def get_confirmed_for_rescan(self, profile: Optional[str] = None) -> list[dict]:
        """Get confirmed removals that are past their next_rescan_at date."""
        conn = self._connect()
        query = """SELECT * FROM removal_requests
            WHERE status = 'confirmed' AND next_rescan_at IS NOT NULL AND next_rescan_at <= ?"""
        params: list[Any] = [_now()]
        if profile:
            query += " AND profile = ?"
            params.append(profile)
        query += " ORDER BY next_rescan_at ASC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def increment_rescan_count(self, removal_id: int) -> None:
        """Bump the rescan_count column for a removal request."""
        conn = self._connect()
        conn.execute(
            "UPDATE removal_requests SET rescan_count = COALESCE(rescan_count, 0) + 1 WHERE id = ?",
            (removal_id,),
        )
        conn.commit()
        conn.close()

    def reset_for_resubmission(self, removal_id: int, rescan_days: int = 90) -> None:
        """Transition a reappeared removal back to pending for resubmission."""
        conn = self._connect()
        row = conn.execute("SELECT status FROM removal_requests WHERE id = ?", (removal_id,)).fetchone()
        if row is None:
            conn.close()
            raise ValueError(f"Removal request {removal_id} not found")
        if row["status"] != "reappeared":
            conn.close()
            raise ValueError(f"Can only reset reappeared removals, got: {row['status']}")
        now = _now()
        conn.execute(
            """UPDATE removal_requests
            SET status = 'pending', submitted_at = NULL, confirmed_at = NULL,
                recheck_at = NULL, next_rescan_at = ?, updated_at = ?
            WHERE id = ?""",
            (_future(rescan_days), now, removal_id),
        )
        conn.commit()
        conn.close()

    def push_next_rescan(self, removal_id: int, days: int = 90) -> None:
        """Push next_rescan_at forward for a confirmed removal that is still clear."""
        conn = self._connect()
        conn.execute(
            "UPDATE removal_requests SET next_rescan_at = ?, updated_at = ? WHERE id = ?",
            (_future(days), _now(), removal_id),
        )
        conn.commit()
        conn.close()


def _now() -> str:
    return datetime.now().isoformat()


def _future(days: int) -> str:
    return (datetime.now() + timedelta(days=days)).isoformat()
