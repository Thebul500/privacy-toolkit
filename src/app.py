"""FastAPI web application for Privacy Toolkit."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.config import (
    Config,
    PROFILES_DIR,
    load_all_brokers,
    load_profile,
    list_profiles,
)
from src.db import Database
from src.models import Profile
from src.tasks import TaskManager, TaskStatus, run_email_removals, run_full_scan

logger = logging.getLogger(__name__)

# Module-level state, initialized in lifespan
config: Config
db: Database
task_manager: TaskManager
scheduler = None

WEB_DIR = Path(__file__).parent / "web"


@asynccontextmanager
async def lifespan(application: FastAPI):
    global config, db, task_manager, scheduler
    config = Config.load()
    db = Database(config.db_path)
    task_manager = TaskManager()

    # Start APScheduler
    from src.scheduler import setup_apscheduler
    try:
        scheduler = setup_apscheduler(config, db, task_manager)
        logger.info("APScheduler started")
    except Exception as e:
        logger.warning("Failed to start scheduler: %s", e)

    db.log("web_app_started")
    yield

    # Shutdown
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Privacy Toolkit", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


# ---------------------------------------------------------------------------
# HTML ROUTES
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    profiles_list = list_profiles()
    findings_count = db.get_findings_count()
    removals = db.get_removals()
    audit = db.get_audit_log(limit=10)

    # Removal breakdown by status
    breakdown: dict[str, int] = {}
    for r in removals:
        s = r.get("status", "unknown")
        breakdown[s] = breakdown.get(s, 0) + 1

    submitted = sum(1 for r in removals if r.get("status") in ("submitted", "confirmed", "rejected"))
    confirmed = sum(1 for r in removals if r.get("status") == "confirmed")

    active = [t for t in task_manager.list_tasks() if t.status == TaskStatus.RUNNING]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active": "dashboard",
        "stats": {
            "profiles": len(profiles_list),
            "findings": findings_count,
            "removals_submitted": submitted,
            "removals_confirmed": confirmed,
            "removal_breakdown": breakdown,
            "profile_names": profiles_list,
        },
        "recent_activity": audit,
        "active_tasks": active,
    })


@app.get("/profiles", response_class=HTMLResponse)
async def profiles_page(request: Request, message: Optional[str] = None,
                        message_type: Optional[str] = None):
    names = list_profiles()
    loaded = []
    for name in names:
        try:
            loaded.append(load_profile(name))
        except Exception as e:
            logger.warning("Failed to load profile %s: %s", name, e)
            loaded.append(Profile(name=name))

    return templates.TemplateResponse("profiles.html", {
        "request": request,
        "active": "profiles",
        "profiles": loaded,
        "message": message,
        "message_type": message_type,
    })


@app.post("/profiles")
async def create_profile(
    request: Request,
    name: str = Form(...),
    first_name: str = Form(""),
    last_name: str = Form(""),
    emails: str = Form(""),
    phones: str = Form(""),
    usernames: str = Form(""),
):
    path = PROFILES_DIR / f"{name}.yaml"
    if path.exists():
        return await profiles_page(request, message=f"Profile '{name}' already exists.",
                                   message_type="error")

    email_list = [e.strip() for e in emails.split(",") if e.strip()]
    phone_list = [p.strip() for p in phones.split(",") if p.strip()]
    uname_list = [u.strip() for u in usernames.split(",") if u.strip()]

    full = f"{first_name} {last_name}".strip()
    p = Profile(
        name=name,
        first_name=first_name,
        last_name=last_name,
        full_name=full,
        email_addresses=email_list,
        phone_numbers=phone_list,
        usernames=uname_list,
    )
    p.to_yaml(path)
    db.log("profile_created", name)
    return RedirectResponse(f"/profiles/{name}", status_code=303)


@app.get("/profiles/{name}", response_class=HTMLResponse)
async def profile_detail(request: Request, name: str):
    try:
        profile = load_profile(name)
    except FileNotFoundError:
        return RedirectResponse("/profiles", status_code=303)

    findings_count = db.get_findings_count(name)
    scans = db.get_scans(profile=name, limit=20)
    removals = db.get_removals(profile=name)

    return templates.TemplateResponse("profile_detail.html", {
        "request": request,
        "active": "profiles",
        "profile": profile,
        "findings_count": findings_count,
        "scans": scans,
        "removals": removals,
    })


@app.get("/scans", response_class=HTMLResponse)
async def scans_page(request: Request, message: Optional[str] = None):
    scans = db.get_scans(limit=100)
    active = [t for t in task_manager.list_tasks() if t.status == TaskStatus.RUNNING]

    return templates.TemplateResponse("scans.html", {
        "request": request,
        "active": "scans",
        "scans": scans,
        "profiles": list_profiles(),
        "active_tasks": active,
        "message": message,
    })


@app.post("/scans/trigger")
async def trigger_scan(profile: str = Form(...)):
    # Verify profile exists
    try:
        loaded = load_profile(profile)
    except FileNotFoundError:
        return RedirectResponse(
            "/scans?message=Profile+not+found&message_type=error", status_code=303
        )

    if not loaded:
        return RedirectResponse(
            "/scans?message=Failed+to+load+profile&message_type=error", status_code=303
        )

    task_id = task_manager.submit(
        f"Full scan: {profile}",
        run_full_scan, profile, config, db,
        profile=profile,
    )
    db.log("scan_triggered", profile, {"task_id": task_id})
    return RedirectResponse(f"/scans?message=Scan+started+for+{profile}+(task+{task_id})", status_code=303)


@app.get("/scans/status/{task_id}", response_class=HTMLResponse)
async def scan_status(request: Request, task_id: str):
    task = task_manager.get(task_id)
    if not task:
        return HTMLResponse("<div class='px-5 py-3 text-sm text-dark-300'>Task not found.</div>")

    if task.status == TaskStatus.RUNNING:
        return HTMLResponse(f"""
        <div class="px-5 py-3 flex justify-between items-center"
             hx-get="/scans/status/{task_id}" hx-trigger="every 3s" hx-swap="outerHTML">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4 text-blue-400 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                </svg>
                <span class="text-sm">{task.name}</span>
            </div>
            <span class="text-xs px-2 py-0.5 rounded bg-blue-900 text-blue-300">running</span>
        </div>
        """)
    elif task.status == TaskStatus.COMPLETED:
        result_text = ""
        if task.result and isinstance(task.result, dict):
            result_text = f" — {task.result.get('total_findings', 0)} findings"
        return HTMLResponse(f"""
        <div class="px-5 py-3 flex justify-between items-center">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
                </svg>
                <span class="text-sm">{task.name}{result_text}</span>
            </div>
            <span class="text-xs px-2 py-0.5 rounded bg-green-900 text-green-300">completed</span>
        </div>
        """)
    else:
        return HTMLResponse(f"""
        <div class="px-5 py-3 flex justify-between items-center">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
                <span class="text-sm">{task.name} — {task.error or 'failed'}</span>
            </div>
            <span class="text-xs px-2 py-0.5 rounded bg-red-900 text-red-300">failed</span>
        </div>
        """)


@app.get("/scans/active", response_class=HTMLResponse)
async def scans_active(request: Request):
    active = [t for t in task_manager.list_tasks() if t.status == TaskStatus.RUNNING]
    if not active:
        return HTMLResponse("")

    rows = []
    for task in active:
        rows.append(f"""
        <div class="px-5 py-3 flex justify-between items-center"
             hx-get="/scans/status/{task.id}" hx-trigger="every 3s" hx-swap="outerHTML">
            <div class="flex items-center gap-2">
                <svg class="w-4 h-4 text-blue-400 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
                </svg>
                <span class="text-sm">{task.name}</span>
            </div>
            <span class="text-xs font-mono text-dark-300">{task.started_at[:16] if task.started_at else ''}</span>
        </div>
        """)

    return HTMLResponse(f"""
    <div class="bg-dark-700 rounded-lg border border-blue-800 mb-6">
        <div class="px-5 py-3 border-b border-dark-600 flex items-center gap-2">
            <svg class="w-4 h-4 text-blue-400 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
            </svg>
            <h3 class="text-sm font-semibold text-blue-300">Running Tasks</h3>
        </div>
        <div class="divide-y divide-dark-600">
            {''.join(rows)}
        </div>
    </div>
    """)


@app.get("/removals", response_class=HTMLResponse)
async def removals_page(request: Request, status: Optional[str] = None,
                        message: Optional[str] = None, message_type: Optional[str] = None):
    removals = db.get_removals(status=status)

    return templates.TemplateResponse("removals.html", {
        "request": request,
        "active": "removals",
        "removals": removals,
        "profiles": list_profiles(),
        "filter_status": status,
        "message": message,
        "message_type": message_type,
    })


@app.post("/removals/email")
async def trigger_email_removals(profile: str = Form(...)):
    try:
        load_profile(profile)
    except FileNotFoundError:
        return RedirectResponse("/removals", status_code=303)

    brokers = load_all_brokers()
    email_slugs = [b.slug for b in brokers if b.email_method]

    if not email_slugs:
        return RedirectResponse("/removals?message=No+brokers+with+email+opt-out+found&message_type=error",
                                status_code=303)

    task_manager.submit(
        f"Email removals: {profile}",
        run_email_removals, profile, email_slugs, config, db,
        profile=profile,
    )
    return RedirectResponse(f"/removals?message=Email+removal+requests+queued+for+{profile}+({len(email_slugs)}+brokers)",
                            status_code=303)


@app.post("/removals/form")
async def trigger_form_removal(
    profile: str = Form(...),
    broker: str = Form(...),
):
    from src.tasks import run_form_removal
    try:
        load_profile(profile)
    except FileNotFoundError:
        return RedirectResponse("/removals?message=Profile+not+found&message_type=error", status_code=303)

    task_manager.submit(
        f"Form removal: {broker}",
        run_form_removal, profile, broker, config, db,
        profile=profile,
    )
    return RedirectResponse(f"/removals?message=Form+removal+queued+for+{broker}", status_code=303)


@app.post("/removals/{removal_id}/confirm")
async def confirm_removal(request: Request, removal_id: int):
    db.update_removal_status(removal_id, "confirmed")
    db.log("removal_confirmed", details={"removal_id": removal_id})

    # For HTMX requests, return the updated row
    if request.headers.get("HX-Request"):
        r = None
        for rem in db.get_removals():
            if rem.get("id") == removal_id:
                r = rem
                break
        if r:
            return HTMLResponse(f"""
            <tr class="hover:bg-dark-600" id="removal-{r['id']}">
                <td class="px-5 py-2 font-mono text-dark-300">#{r['id']}</td>
                <td class="px-5 py-2">{r['profile']}</td>
                <td class="px-5 py-2 font-medium text-white">{r['broker_name']}</td>
                <td class="px-5 py-2">{r['method']}</td>
                <td class="px-5 py-2"><span class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-green-900/50 text-green-300">confirmed</span></td>
                <td class="px-5 py-2 text-dark-300 font-mono text-xs">{r.get('submitted_at', '—')[:10] if r.get('submitted_at') else '—'}</td>
                <td class="px-5 py-2 text-dark-300 font-mono text-xs">{r.get('recheck_at', '—')[:10] if r.get('recheck_at') else '—'}</td>
                <td class="px-5 py-2 text-right">
                    <form method="post" action="/removals/{r['id']}/reappeared" class="inline"
                          hx-post="/removals/{r['id']}/reappeared" hx-target="#removal-{r['id']}" hx-swap="outerHTML">
                        <button type="submit" class="px-2 py-0.5 text-xs bg-red-800 hover:bg-red-700 rounded text-red-200 transition-colors">
                            Reappeared
                        </button>
                    </form>
                </td>
            </tr>
            """)

    return RedirectResponse("/removals", status_code=303)


@app.post("/removals/{removal_id}/reappeared")
async def reappeared_removal(request: Request, removal_id: int):
    db.update_removal_status(removal_id, "reappeared")
    db.log("removal_reappeared", details={"removal_id": removal_id})

    if request.headers.get("HX-Request"):
        r = None
        for rem in db.get_removals():
            if rem.get("id") == removal_id:
                r = rem
                break
        if r:
            return HTMLResponse(f"""
            <tr class="hover:bg-dark-600" id="removal-{r['id']}">
                <td class="px-5 py-2 font-mono text-dark-300">#{r['id']}</td>
                <td class="px-5 py-2">{r['profile']}</td>
                <td class="px-5 py-2 font-medium text-white">{r['broker_name']}</td>
                <td class="px-5 py-2">{r['method']}</td>
                <td class="px-5 py-2"><span class="inline-flex items-center px-2 py-0.5 rounded text-xs bg-red-900/50 text-red-300">reappeared</span></td>
                <td class="px-5 py-2 text-dark-300 font-mono text-xs">{r.get('submitted_at', '—')[:10] if r.get('submitted_at') else '—'}</td>
                <td class="px-5 py-2 text-dark-300 font-mono text-xs">{r.get('recheck_at', '—')[:10] if r.get('recheck_at') else '—'}</td>
                <td class="px-5 py-2 text-right"></td>
            </tr>
            """)

    return RedirectResponse("/removals", status_code=303)


@app.get("/brokers", response_class=HTMLResponse)
async def brokers_page(request: Request, priority: Optional[str] = None):
    brokers = load_all_brokers()
    if priority:
        brokers = [b for b in brokers if b.priority.value == priority]

    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    brokers.sort(key=lambda b: priority_order.get(b.priority.value, 4))

    return templates.TemplateResponse("brokers.html", {
        "request": request,
        "active": "brokers",
        "brokers": brokers,
        "filter_priority": priority,
    })


@app.get("/activity", response_class=HTMLResponse)
async def activity_page(request: Request):
    entries = db.get_audit_log(limit=200)

    return templates.TemplateResponse("activity.html", {
        "request": request,
        "active": "activity",
        "entries": entries,
    })


# ---------------------------------------------------------------------------
# API ROUTES (JSON)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def api_health():
    return {"status": "ok", "tasks_active": task_manager.active_count}


@app.get("/api/stats")
async def api_stats():
    profiles_list = list_profiles()
    findings_count = db.get_findings_count()
    removals = db.get_removals()

    breakdown: dict[str, int] = {}
    for r in removals:
        s = r.get("status", "unknown")
        breakdown[s] = breakdown.get(s, 0) + 1

    return {
        "profiles": len(profiles_list),
        "findings": findings_count,
        "removals_total": len(removals),
        "removals_by_status": breakdown,
        "brokers_configured": len(load_all_brokers()),
        "tasks_active": task_manager.active_count,
    }
