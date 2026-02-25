"""Cron scheduling for periodic re-scans + APScheduler for web mode."""

from __future__ import annotations
import logging
import subprocess
from typing import TYPE_CHECKING

from src.config import TOOLKIT_DIR, ScheduleConfig

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

    from src.config import Config
    from src.db import Database
    from src.tasks import TaskManager

logger = logging.getLogger(__name__)

MARKER_START = "# === Privacy Toolkit ==="
MARKER_END = "# === End Privacy Toolkit ==="


def get_venv_python() -> str:
    return str(TOOLKIT_DIR / ".venv" / "bin" / "python")


def get_cli_cmd() -> str:
    return f'{get_venv_python()} -m src.cli'


def generate_cron_lines(profile: str, config: ScheduleConfig) -> list[str]:
    cli = get_cli_cmd()
    log_dir = TOOLKIT_DIR / "data" / "logs"

    lines = [
        MARKER_START,
        "# Weekly exposure re-scan",
        f"{config.cron_time} cd {TOOLKIT_DIR} && {cli} scan full -p {profile} >> {log_dir}/cron-scan.log 2>&1",
        "# Daily pending follow-up check",
        f"0 9 * * * cd {TOOLKIT_DIR} && {cli} track pending -p {profile} >> {log_dir}/cron-pending.log 2>&1",
        "# Weekly follow-up emails for overdue removals (Monday 10 AM)",
        f"0 10 * * 1 cd {TOOLKIT_DIR} && {cli} -p {profile} remove follow-up >> {log_dir}/cron-followup.log 2>&1",
        MARKER_END,
    ]
    return lines


def install_cron(profile: str, config: ScheduleConfig) -> bool:
    # Get current crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""

    # Remove old privacy toolkit entries
    clean = _remove_markers(existing)

    # Add new entries
    new_lines = generate_cron_lines(profile, config)
    new_crontab = clean.rstrip() + "\n\n" + "\n".join(new_lines) + "\n"

    # Install
    proc = subprocess.run(
        ["crontab", "-"],
        input=new_crontab,
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def remove_cron() -> bool:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return True
    clean = _remove_markers(result.stdout)
    proc = subprocess.run(
        ["crontab", "-"],
        input=clean,
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def get_cron_status() -> dict:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return {"installed": False, "lines": []}

    in_section = False
    lines = []
    for line in result.stdout.splitlines():
        if MARKER_START in line:
            in_section = True
            continue
        if MARKER_END in line:
            in_section = False
            continue
        if in_section and line.strip() and not line.strip().startswith("#"):
            lines.append(line.strip())

    return {"installed": bool(lines), "lines": lines}


def _remove_markers(text: str) -> str:
    lines = text.splitlines()
    result = []
    in_section = False
    for line in lines:
        if MARKER_START in line:
            in_section = True
            continue
        if MARKER_END in line:
            in_section = False
            continue
        if not in_section:
            result.append(line)
    return "\n".join(result)


# ---------------------------------------------------------------------------
# APScheduler for web mode
# ---------------------------------------------------------------------------

def _scheduled_scan(profile_name: str, config: "Config", db: "Database",
                    task_manager: "TaskManager") -> None:
    """Called by APScheduler to run a full scan."""
    from src.tasks import run_full_scan
    logger.info("Scheduled scan starting for profile: %s", profile_name)
    task_manager.submit(
        f"Scheduled scan: {profile_name}",
        run_full_scan, profile_name, config, db,
        profile=profile_name,
    )


def _scheduled_verification(profile_name: str, config: "Config", db: "Database",
                            task_manager: "TaskManager") -> None:
    """Called by APScheduler to run verification scans."""
    from src.tasks import run_verification_scans
    logger.info("Scheduled verification scan starting for profile: %s", profile_name)
    task_manager.submit(
        f"Verification scan: {profile_name}",
        run_verification_scans, profile_name, config, db,
        profile=profile_name,
    )


def _scheduled_confirmed_rescan(profile_name: str, config: "Config", db: "Database",
                                task_manager: "TaskManager") -> None:
    """Re-scan confirmed removals to check for re-listing."""
    from src.tasks import run_confirmed_rescan
    logger.info("Scheduled confirmed rescan starting for profile: %s", profile_name)
    task_manager.submit(
        f"Confirmed rescan: {profile_name}",
        run_confirmed_rescan, profile_name, config, db,
        profile=profile_name,
    )


def _scheduled_digest(config: "Config", db: "Database",
                      task_manager: "TaskManager") -> None:
    """Send the weekly privacy digest."""
    from src.digest import send_digest
    logger.info("Generating weekly digest")
    try:
        send_digest(db, config, period="weekly")
    except Exception as e:
        logger.error("Failed to send weekly digest: %s", e)


def _scheduled_follow_ups(config: "Config", db: "Database",
                          task_manager: "TaskManager") -> None:
    """Check for overdue removals and send follow-up emails."""
    from src.tasks import run_follow_ups
    logger.info("Checking for overdue removal requests needing follow-up")
    task_manager.submit(
        "Follow-up emails",
        run_follow_ups, config, db,
    )


def setup_apscheduler(config: "Config", db: "Database",
                      task_manager: "TaskManager") -> "BackgroundScheduler":
    """Create and start an APScheduler BackgroundScheduler from config.

    Returns the scheduler instance (caller should keep a reference).
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    from src.config import list_profiles

    scheduler = BackgroundScheduler()

    # Parse cron_time "minute hour dom month dow"
    parts = config.schedule.cron_time.split()
    if len(parts) == 5:
        minute, hour, day, month, dow = parts
    else:
        minute, hour, day, month, dow = "0", "3", "*", "*", "0"

    profiles = list_profiles()
    for profile_name in profiles:
        # Weekly full scan per the configured schedule
        scheduler.add_job(
            _scheduled_scan,
            CronTrigger(minute=minute, hour=hour, day=day, month=month,
                        day_of_week=dow),
            args=[profile_name, config, db, task_manager],
            id=f"scan_{profile_name}",
            name=f"Weekly scan: {profile_name}",
            replace_existing=True,
        )
        logger.info("Scheduled weekly scan for '%s' at %s", profile_name,
                     config.schedule.cron_time)

        # Daily pending recheck at 9 AM
        scheduler.add_job(
            _scheduled_scan,
            CronTrigger(hour=9, minute=0),
            args=[profile_name, config, db, task_manager],
            id=f"recheck_{profile_name}",
            name=f"Daily recheck: {profile_name}",
            replace_existing=True,
        )

    # Daily verification scans at 11 AM
    for profile_name in profiles:
        scheduler.add_job(
            _scheduled_verification,
            CronTrigger(hour=11, minute=0),
            args=[profile_name, config, db, task_manager],
            id=f"verify_{profile_name}",
            name=f"Daily verification: {profile_name}",
            replace_existing=True,
        )
    logger.info("Scheduled daily verification scans at 11 AM")

    # Daily follow-up check at 10 AM for overdue removals
    scheduler.add_job(
        _scheduled_follow_ups,
        CronTrigger(hour=10, minute=0),
        args=[config, db, task_manager],
        id="follow_up_check",
        name="Daily follow-up check",
        replace_existing=True,
    )
    logger.info("Scheduled daily follow-up check at 10 AM")

    # Weekly confirmed rescan (Wednesdays 2 PM)
    for profile_name in profiles:
        scheduler.add_job(
            _scheduled_confirmed_rescan,
            CronTrigger(day_of_week="wed", hour=14, minute=0),
            args=[profile_name, config, db, task_manager],
            id=f"confirmed_rescan_{profile_name}",
            name=f"Confirmed rescan: {profile_name}",
            replace_existing=True,
        )
    logger.info("Scheduled weekly confirmed rescan (Wed 2 PM)")

    # Weekly digest (Sunday 8 PM)
    scheduler.add_job(
        _scheduled_digest,
        CronTrigger(day_of_week="sun", hour=20, minute=0),
        args=[config, db, task_manager],
        id="weekly_digest",
        name="Weekly digest",
        replace_existing=True,
    )
    logger.info("Scheduled weekly digest (Sun 8 PM)")

    scheduler.start()
    logger.info("APScheduler started with %d job(s)", len(scheduler.get_jobs()))
    return scheduler
