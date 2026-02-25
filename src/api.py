"""REST API router for Privacy Toolkit — JSON endpoints with API key auth."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


def _get_state(request: Request):
    """Retrieve module-level state from the main app module."""
    from src import app as app_module
    return app_module.db, app_module.config, app_module.task_manager


# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------

@router.get("/health")
async def api_health(request: Request):
    _, _, task_manager = _get_state(request)
    return {"status": "ok", "tasks_active": task_manager.active_count}


@router.get("/stats")
async def api_stats(request: Request):
    from src.config import list_profiles, load_all_brokers
    db, _, task_manager = _get_state(request)

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


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

@router.get("/profiles")
async def api_profiles(request: Request):
    from src.config import list_profiles, load_profile
    db, _, _ = _get_state(request)

    names = list_profiles()
    result = []
    for name in names:
        try:
            p = load_profile(name)
            result.append({
                "name": p.name,
                "first_name": p.first_name,
                "last_name": p.last_name,
                "emails": len(p.email_addresses),
                "phones": len(p.phone_numbers),
                "usernames": len(p.usernames),
            })
        except Exception:
            result.append({"name": name, "error": "failed to load"})
    return result


@router.get("/profiles/{name}")
async def api_profile_detail(request: Request, name: str):
    from src.config import load_profile
    from src.scoring import calculate_score, get_trend
    db, _, _ = _get_state(request)

    try:
        p = load_profile(name)
    except FileNotFoundError:
        raise HTTPException(404, f"Profile '{name}' not found")

    score_data = None
    try:
        ps = calculate_score(db, name)
        trend = get_trend(db, name)
        score_data = {
            "score": ps.score,
            "grade": ps.grade,
            "findings_count": ps.findings_count,
            "breaches_count": ps.breaches_count,
            "broker_listings": ps.broker_listings,
            "removals_confirmed": ps.removals_confirmed,
            "removals_pending": ps.removals_pending,
            "trend": trend,
        }
    except Exception:
        pass

    return {
        "name": p.name,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "full_name": p.full_name,
        "email_addresses": p.email_addresses,
        "phone_numbers": p.phone_numbers,
        "usernames": p.usernames,
        "score": score_data,
    }


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------

@router.post("/scans")
async def api_trigger_scan(request: Request):
    from src.config import load_profile
    from src.tasks import run_full_scan
    db, config, task_manager = _get_state(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    profile_name = body.get("profile")
    if not profile_name:
        raise HTTPException(400, "Missing 'profile' field")

    try:
        load_profile(profile_name)
    except FileNotFoundError:
        raise HTTPException(404, f"Profile '{profile_name}' not found")

    task_id = task_manager.submit(
        f"API scan: {profile_name}",
        run_full_scan, profile_name, config, db,
        profile=profile_name,
    )
    return {"task_id": task_id, "profile": profile_name, "status": "started"}


@router.get("/scans")
async def api_list_scans(request: Request, profile: Optional[str] = None,
                         limit: int = Query(50, ge=1, le=500)):
    db, _, _ = _get_state(request)
    return db.get_scans(profile=profile, limit=limit)


@router.get("/scans/{task_id}")
async def api_scan_status(request: Request, task_id: str):
    _, _, task_manager = _get_state(request)
    task = task_manager.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    return {
        "id": task.id,
        "name": task.name,
        "status": task.status.value,
        "started_at": task.started_at,
        "completed_at": task.completed_at,
        "result": task.result,
        "error": task.error,
        "profile": task.profile,
    }


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

@router.get("/findings")
async def api_findings(request: Request, profile: Optional[str] = None,
                       source: Optional[str] = None):
    db, _, _ = _get_state(request)
    return db.get_findings(profile=profile, source=source)


# ---------------------------------------------------------------------------
# Removals
# ---------------------------------------------------------------------------

@router.get("/removals")
async def api_removals(request: Request, profile: Optional[str] = None,
                       status: Optional[str] = None):
    db, _, _ = _get_state(request)
    return db.get_removals(profile=profile, status=status)


@router.post("/removals")
async def api_trigger_removals(request: Request):
    from src.config import load_profile
    from src.tasks import run_email_removals
    db, config, task_manager = _get_state(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    profile_name = body.get("profile")
    broker_slugs = body.get("broker_slugs", [])
    if not profile_name:
        raise HTTPException(400, "Missing 'profile' field")
    if not broker_slugs:
        raise HTTPException(400, "Missing 'broker_slugs' field")

    try:
        load_profile(profile_name)
    except FileNotFoundError:
        raise HTTPException(404, f"Profile '{profile_name}' not found")

    task_id = task_manager.submit(
        f"API removals: {profile_name}",
        run_email_removals, profile_name, broker_slugs, config, db,
        profile=profile_name,
    )
    return {"task_id": task_id, "profile": profile_name, "broker_slugs": broker_slugs}


@router.get("/removals/{removal_id}")
async def api_removal_detail(request: Request, removal_id: int):
    db, _, _ = _get_state(request)
    removals = db.get_removals()
    for r in removals:
        if r.get("id") == removal_id:
            return r
    raise HTTPException(404, "Removal not found")


@router.patch("/removals/{removal_id}")
async def api_update_removal(request: Request, removal_id: int):
    db, _, _ = _get_state(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")

    new_status = body.get("status")
    if not new_status:
        raise HTTPException(400, "Missing 'status' field")

    try:
        db.update_removal_status(removal_id, new_status)
    except ValueError as e:
        raise HTTPException(400, str(e))

    return {"id": removal_id, "status": new_status}


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

@router.get("/score/{profile}")
async def api_score(request: Request, profile: str):
    from src.scoring import calculate_score, get_trend
    db, _, _ = _get_state(request)

    try:
        ps = calculate_score(db, profile)
        trend = get_trend(db, profile)
    except Exception as e:
        raise HTTPException(500, f"Score calculation failed: {e}")

    return {
        "profile": profile,
        "score": ps.score,
        "grade": ps.grade,
        "trend": trend,
        "risk_factors": ps.risk_factors,
        "recommendations": ps.recommendations,
    }


@router.get("/score/{profile}/history")
async def api_score_history(request: Request, profile: str,
                            limit: int = Query(90, ge=1, le=365)):
    db, _, _ = _get_state(request)
    return db.get_score_history(profile, limit=limit)


# ---------------------------------------------------------------------------
# Brokers
# ---------------------------------------------------------------------------

@router.get("/brokers")
async def api_brokers(request: Request):
    from src.config import load_all_brokers
    db, _, _ = _get_state(request)

    brokers = load_all_brokers()
    compliance = {c["broker_slug"]: c for c in db.get_broker_compliance()}

    result = []
    for b in brokers:
        entry = {
            "slug": b.slug,
            "name": b.name,
            "url": b.url,
            "category": b.category,
            "priority": b.priority.value,
            "data_types": b.data_types,
            "has_email": b.email_method is not None,
            "has_form": b.form_method is not None,
        }
        if b.slug in compliance:
            entry["compliance"] = compliance[b.slug]
        result.append(entry)
    return result


@router.get("/brokers/{slug}/compliance")
async def api_broker_compliance(request: Request, slug: str):
    db, _, _ = _get_state(request)
    results = db.get_broker_compliance(broker_slug=slug)
    if not results:
        raise HTTPException(404, f"No compliance data for broker '{slug}'")
    return results[0]


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@router.get("/tasks")
async def api_tasks(request: Request):
    _, _, task_manager = _get_state(request)
    tasks = task_manager.list_tasks()
    return [
        {
            "id": t.id,
            "name": t.name,
            "status": t.status.value,
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "profile": t.profile,
        }
        for t in tasks
    ]
