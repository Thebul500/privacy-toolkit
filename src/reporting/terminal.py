"""Rich terminal output for scan results and tracking."""

from __future__ import annotations
from typing import Optional

from rich.console import Console
from rich.table import Table

from src.db import Database


def show_scan_results(db: Database, profile: Optional[str] = None, console: Console | None = None) -> None:
    console = console or Console()
    findings = db.get_findings(profile=profile)

    if not findings:
        console.print("[yellow]No scan results found.[/yellow]")
        if profile:
            console.print(f"Run: [bold]privacy-toolkit scan full -p {profile}[/bold]")
        return

    table = Table(title="Exposure Report", show_lines=True)
    table.add_column("Source", style="cyan", width=12)
    table.add_column("Site", style="bold", width=25)
    table.add_column("Type", width=18)
    table.add_column("URL", style="dim", max_width=50, overflow="fold")
    table.add_column("Confidence", width=10)

    for f in findings:
        conf_style = {"high": "red", "medium": "yellow", "low": "dim"}.get(f["confidence"], "")
        table.add_row(
            f["source"],
            f["site_name"],
            f["data_type"],
            f.get("site_url", ""),
            f"[{conf_style}]{f['confidence']}[/{conf_style}]",
        )

    console.print(table)
    console.print(f"\n[bold]{len(findings)}[/bold] exposures found across all scans.")


def show_removal_status(db: Database, profile: Optional[str] = None, console: Console | None = None) -> None:
    console = console or Console()
    removals = db.get_removals(profile=profile)

    if not removals:
        console.print("[yellow]No removal requests found.[/yellow]")
        return

    table = Table(title="Removal Request Status", show_lines=True)
    table.add_column("ID", style="dim", width=4)
    table.add_column("Broker", style="bold", width=25)
    table.add_column("Method", width=8)
    table.add_column("Status", width=15)
    table.add_column("Submitted", width=12)
    table.add_column("Recheck", width=12)

    status_colors = {
        "pending": "yellow",
        "submitted": "blue",
        "confirmed": "green",
        "rejected": "red",
        "reappeared": "red bold",
        "pending_captcha": "yellow",
    }

    for r in removals:
        status = r["status"]
        color = status_colors.get(status, "")
        submitted = (r.get("submitted_at") or "")[:10]
        recheck = (r.get("recheck_at") or "")[:10]
        table.add_row(
            str(r["id"]),
            r["broker_name"],
            r["method"],
            f"[{color}]{status}[/{color}]",
            submitted,
            recheck,
        )

    console.print(table)

    by_status: dict[str, int] = {}
    for r in removals:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    parts = [f"{v} {k}" for k, v in sorted(by_status.items())]
    console.print(f"\nTotal: {len(removals)} requests ({', '.join(parts)})")


def show_pending_rechecks(db: Database, profile: Optional[str] = None, console: Console | None = None) -> None:
    console = console or Console()
    pending = db.get_pending_rechecks(profile=profile)

    if not pending:
        console.print("[green]No pending follow-ups.[/green]")
        return

    table = Table(title="Pending Follow-ups (Recheck Due)", show_lines=True)
    table.add_column("ID", width=4)
    table.add_column("Broker", style="bold", width=25)
    table.add_column("Method", width=8)
    table.add_column("Submitted", width=12)
    table.add_column("Recheck Due", style="red", width=12)

    for r in pending:
        table.add_row(
            str(r["id"]),
            r["broker_name"],
            r["method"],
            (r.get("submitted_at") or "")[:10],
            (r.get("recheck_at") or "")[:10],
        )

    console.print(table)
    console.print(f"\n[bold red]{len(pending)}[/bold red] requests need follow-up verification.")


def show_scan_history(db: Database, profile: Optional[str] = None, console: Console | None = None) -> None:
    console = console or Console()
    scans = db.get_scans(profile=profile)

    if not scans:
        console.print("[yellow]No scan history found.[/yellow]")
        return

    table = Table(title="Scan History", show_lines=True)
    table.add_column("ID", width=4)
    table.add_column("Scanner", style="cyan", width=14)
    table.add_column("Query", width=25)
    table.add_column("Status", width=10)
    table.add_column("Results", width=8)
    table.add_column("Date", width=12)

    for s in scans:
        status = s["status"]
        color = {"completed": "green", "failed": "red", "running": "yellow"}.get(status, "")
        table.add_row(
            str(s["id"]),
            s["scanner"],
            s["query"][:25],
            f"[{color}]{status}[/{color}]",
            str(s["result_count"]),
            (s.get("started_at") or "")[:10],
        )

    console.print(table)
