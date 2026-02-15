"""Background task runner for long-running scan/removal jobs."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskInfo:
    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Any = None
    error: Optional[str] = None
    profile: Optional[str] = None


class TaskManager:
    """Manages background tasks using a thread pool."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, TaskInfo] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, fn: Callable, *args: Any,
               profile: Optional[str] = None, **kwargs: Any) -> str:
        task_id = uuid.uuid4().hex[:12]
        info = TaskInfo(id=task_id, name=name, profile=profile)

        with self._lock:
            self._tasks[task_id] = info

        def _wrapper():
            with self._lock:
                info.status = TaskStatus.RUNNING
                info.started_at = datetime.now().isoformat()
            try:
                result = fn(*args, **kwargs)
                with self._lock:
                    info.status = TaskStatus.COMPLETED
                    info.result = result
                    info.completed_at = datetime.now().isoformat()
                logger.info("Task %s (%s) completed", task_id, name)
            except Exception as e:
                with self._lock:
                    info.status = TaskStatus.FAILED
                    info.error = str(e)
                    info.completed_at = datetime.now().isoformat()
                logger.error("Task %s (%s) failed: %s", task_id, name, e)

        self._executor.submit(_wrapper)
        return task_id

    def get(self, task_id: str) -> Optional[TaskInfo]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> list[TaskInfo]:
        with self._lock:
            tasks = list(self._tasks.values())
        return sorted(tasks, key=lambda t: t.started_at or "", reverse=True)[:limit]

    @property
    def active_count(self) -> int:
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING)


def run_full_scan(profile_name: str, config, db) -> dict:
    """Run a full scan for a profile. Reuses the same logic as cli.py scan_full."""
    from src.config import load_profile
    from src.notifications import send_signal

    profile = load_profile(profile_name)
    total = 0

    # Username scans
    if profile.usernames:
        try:
            from src.scanners.sherlock_scanner import SherlockScanner
            scanner = SherlockScanner()
            if scanner.is_available():
                for username in profile.usernames:
                    scan_id = db.create_scan(profile_name, scanner.name, "username", username)
                    try:
                        results = scanner.scan(username)
                        for r in results:
                            db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                           r.site_url, r.data_type, r.details, r.confidence)
                        db.complete_scan(scan_id, len(results))
                        total += len(results)
                    except Exception as e:
                        db.fail_scan(scan_id, str(e))
        except ImportError:
            pass

        try:
            from src.scanners.maigret_scanner import MaigretScanner
            scanner = MaigretScanner()
            if scanner.is_available():
                for username in profile.usernames:
                    scan_id = db.create_scan(profile_name, scanner.name, "username", username)
                    try:
                        results = scanner.scan(username)
                        for r in results:
                            db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                           r.site_url, r.data_type, r.details, r.confidence)
                        db.complete_scan(scan_id, len(results))
                        total += len(results)
                    except Exception as e:
                        db.fail_scan(scan_id, str(e))
        except ImportError:
            pass

    # Email scans
    if profile.email_addresses:
        try:
            from src.scanners.holehe_scanner import HoleheScanner
            scanner = HoleheScanner()
            if scanner.is_available():
                for email in profile.email_addresses:
                    scan_id = db.create_scan(profile_name, scanner.name, "email", email)
                    try:
                        results = scanner.scan(email)
                        for r in results:
                            db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                           r.site_url, r.data_type, r.details, r.confidence)
                        db.complete_scan(scan_id, len(results))
                        total += len(results)
                    except Exception as e:
                        db.fail_scan(scan_id, str(e))
        except ImportError:
            pass

        try:
            from src.scanners.hibp_scanner import HIBPScanner
            scanner = HIBPScanner(api_key=config.hibp_api_key)
            for email in profile.email_addresses:
                scan_id = db.create_scan(profile_name, scanner.name, "email", email)
                try:
                    results = scanner.scan(email)
                    for r in results:
                        db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                       r.site_url, r.data_type, r.details, r.confidence)
                    db.complete_scan(scan_id, len(results))
                    total += len(results)
                except Exception as e:
                    db.fail_scan(scan_id, str(e))
        except ImportError:
            pass

    # Phone scans
    if profile.phone_numbers:
        try:
            from src.scanners.phoneinfoga_scanner import PhoneInfogaScanner
            scanner = PhoneInfogaScanner()
            if scanner.is_available():
                for phone in profile.phone_numbers:
                    scan_id = db.create_scan(profile_name, scanner.name, "phone", phone)
                    try:
                        results = scanner.scan(phone)
                        for r in results:
                            db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                           r.site_url, r.data_type, r.details, r.confidence)
                        db.complete_scan(scan_id, len(results))
                        total += len(results)
                    except Exception as e:
                        db.fail_scan(scan_id, str(e))
        except ImportError:
            pass

    # People search scans
    try:
        from src.scanners.people_search_scanner import PeopleSearchScanner
        ps = PeopleSearchScanner()
        if ps.is_available():
            if profile.first_name and profile.last_name:
                state = ""
                if profile.addresses:
                    state = profile.addresses[0].state_abbr or profile.addresses[0].state
                name_query = f"{profile.first_name} {profile.last_name}"
                if state:
                    name_query += f" {state}"
                scan_id = db.create_scan(profile_name, "people_search", "name", name_query)
                try:
                    results = ps.scan(name_query, "name")
                    for r in results:
                        db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                       r.site_url, r.data_type, r.details, r.confidence)
                    db.complete_scan(scan_id, len(results))
                    total += len(results)
                except Exception as e:
                    db.fail_scan(scan_id, str(e))

            for phone in profile.phone_numbers:
                scan_id = db.create_scan(profile_name, "people_search", "phone", phone)
                try:
                    results = ps.scan(phone, "phone")
                    for r in results:
                        db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                       r.site_url, r.data_type, r.details, r.confidence)
                    db.complete_scan(scan_id, len(results))
                    total += len(results)
                except Exception as e:
                    db.fail_scan(scan_id, str(e))

            for email in profile.email_addresses:
                scan_id = db.create_scan(profile_name, "people_search", "email", email)
                try:
                    results = ps.scan(email, "email")
                    for r in results:
                        db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                       r.site_url, r.data_type, r.details, r.confidence)
                    db.complete_scan(scan_id, len(results))
                    total += len(results)
                except Exception as e:
                    db.fail_scan(scan_id, str(e))

            for addr in profile.addresses:
                if addr.street and addr.city and (addr.state_abbr or addr.state):
                    state = addr.state_abbr or addr.state
                    addr_query = f"{addr.street}|{addr.city}|{state}|{addr.zip_code}"
                    scan_id = db.create_scan(profile_name, "people_search", "address", addr_query)
                    try:
                        results = ps.scan(addr_query, "address")
                        for r in results:
                            db.add_finding(scan_id, profile_name, r.scanner, r.site_name,
                                           r.site_url, r.data_type, r.details, r.confidence)
                        db.complete_scan(scan_id, len(results))
                        total += len(results)
                    except Exception as e:
                        db.fail_scan(scan_id, str(e))
    except ImportError:
        pass

    # Notify
    if config.signal.enabled:
        send_signal(
            f"Privacy Toolkit: Full scan complete for {profile_name}. {total} exposures found.",
            config.signal,
        )

    db.log("full_scan_complete", profile_name, {"total_findings": total})
    return {"profile": profile_name, "total_findings": total}


def run_email_removals(profile_name: str, broker_slugs: list[str], config, db) -> dict:
    """Send email removal requests for specified brokers."""
    from src.config import load_broker, load_profile
    from src.removers.email_remover import EmailRemover

    profile = load_profile(profile_name)
    remover = EmailRemover(config.smtp, db)
    sent = 0
    errors = []

    for slug in broker_slugs:
        try:
            broker = load_broker(slug)
            result = remover.send_removal_request(broker, profile)
            if result.get("success"):
                sent += 1
            else:
                errors.append(f"{slug}: {result.get('error', 'unknown')}")
        except Exception as e:
            errors.append(f"{slug}: {e}")

    db.log("email_removals_sent", profile_name, {"sent": sent, "errors": errors})
    return {"sent": sent, "errors": errors}


def run_form_removal(profile_name: str, broker_slug: str, config, db) -> dict:
    """Run a single form-based opt-out."""
    from src.config import load_broker, load_profile
    from src.removers.form_remover import FormRemover

    profile = load_profile(profile_name)
    broker = load_broker(broker_slug)
    remover = FormRemover(config.browser, db)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(remover.submit_opt_out(broker, profile))
    finally:
        loop.close()

    db.log("form_removal", profile_name, {"broker": broker_slug, "success": result.get("success")})
    return result


def run_follow_ups(config, db) -> dict:
    """Check for overdue removals and send follow-up emails."""
    from src.config import load_broker, load_profile
    from src.removers.email_remover import EmailRemover

    overdue = db.get_overdue_removals(days=45)
    if not overdue:
        logger.info("No overdue removals needing follow-up")
        return {"sent": 0, "checked": 0}

    remover = EmailRemover(config.smtp, db)
    sent = 0
    errors = []

    for removal in overdue:
        try:
            profile = load_profile(removal["profile"])
            broker = load_broker(removal["broker_slug"])
            result = remover.send_follow_up(removal, profile, broker)
            if result.get("success"):
                sent += 1
                logger.info("Follow-up sent for %s -> %s", removal["profile"], removal["broker_slug"])
            else:
                errors.append(f"{removal['broker_slug']}: {result.get('error')}")
        except Exception as e:
            errors.append(f"{removal['broker_slug']}: {e}")
            logger.error("Follow-up failed for %s: %s", removal["broker_slug"], e)

    db.log("follow_ups_sent", None, {"sent": sent, "checked": len(overdue), "errors": errors})
    return {"sent": sent, "checked": len(overdue), "errors": errors}
