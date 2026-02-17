"""Privacy Toolkit CLI - Discover, remove, and track personal data exposure."""

from __future__ import annotations
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.config import (
    Config, PROFILES_DIR, TOOLKIT_DIR,
    load_all_brokers, load_broker, load_profile, list_profiles,
)
from src.db import Database
from src.models import Profile

console = Console()


def get_db(config: Config) -> Database:
    return Database(config.db_path)


@click.group()
@click.option("--profile", "-p", default=None, help="Profile name to use")
@click.option("--config", "-c", default=None, help="Config file path")
@click.pass_context
def cli(ctx, profile, config):
    """Privacy Toolkit - Discover, remove, and track personal data exposure."""
    ctx.ensure_object(dict)
    config_path = Path(config) if config else None
    ctx.obj["config"] = Config.load(config_path)
    ctx.obj["profile_name"] = profile
    ctx.obj["db"] = get_db(ctx.obj["config"])


# ============================================================================
# SCAN COMMANDS
# ============================================================================

@cli.group()
def scan():
    """Run discovery scans to find where your data is exposed."""
    pass


@scan.command("username")
@click.argument("usernames", nargs=-1, required=True)
@click.pass_context
def scan_username(ctx, usernames):
    """Search for usernames across social networks (Sherlock + Maigret)."""
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"] or "cli"

    from src.scanners.sherlock_scanner import SherlockScanner
    from src.scanners.maigret_scanner import MaigretScanner

    scanners = []
    sherlock = SherlockScanner()
    maigret = MaigretScanner()

    if sherlock.is_available():
        scanners.append(sherlock)
    else:
        console.print("[yellow]Sherlock not available. Skipping.[/yellow]")

    if maigret.is_available():
        scanners.append(maigret)
    else:
        console.print("[yellow]Maigret not available. Skipping.[/yellow]")

    if not scanners:
        console.print("[red]No username scanners available. Run install.sh first.[/red]")
        return

    total_results = 0
    for username in usernames:
        if not username.strip():
            click.echo("Warning: Skipping empty username.", err=True)
            continue
        console.print(f"\n[bold]Scanning username: {username}[/bold]")
        for scanner in scanners:
            scan_id = db.create_scan(profile_name, scanner.name, "username", username)
            console.print(f"  Running {scanner.name}...", end=" ")
            try:
                results = scanner.scan(username)
                for r in results:
                    db.add_finding(
                        scan_id, profile_name, r.scanner, r.site_name,
                        r.site_url, r.data_type, r.details, r.confidence,
                    )
                db.complete_scan(scan_id, len(results))
                console.print(f"[green]{len(results)} found[/green]")
                total_results += len(results)
            except Exception as e:
                db.fail_scan(scan_id, str(e))
                console.print(f"[red]failed: {e}[/red]")

    console.print(f"\n[bold]Total: {total_results} exposures found.[/bold]")
    console.print("Run [bold]privacy-toolkit report[/bold] to view details.")


@scan.command("email")
@click.argument("emails", nargs=-1, required=True)
@click.pass_context
def scan_email(ctx, emails):
    """Check which services an email is registered on (Holehe + HIBP)."""
    db = ctx.obj["db"]
    config = ctx.obj["config"]
    profile_name = ctx.obj["profile_name"] or "cli"

    from src.scanners.holehe_scanner import HoleheScanner
    from src.scanners.hibp_scanner import HIBPScanner

    scanners = []
    holehe = HoleheScanner()
    if holehe.is_available():
        scanners.append(holehe)
    else:
        console.print("[yellow]Holehe not available. Skipping.[/yellow]")

    hibp_key = getattr(config, "hibp_api_key", "")
    hibp = HIBPScanner(api_key=hibp_key)
    scanners.append(hibp)

    if not scanners:
        console.print("[red]No email scanners available. Run install.sh first.[/red]")
        return

    total_results = 0
    for email in emails:
        if "@" not in email:
            click.echo(f"Warning: Skipping invalid email (missing @): {email}", err=True)
            continue
        console.print(f"\n[bold]Scanning email: {email}[/bold]")
        for scanner in scanners:
            scan_id = db.create_scan(profile_name, scanner.name, "email", email)
            console.print(f"  Running {scanner.name}...", end=" ")
            try:
                results = scanner.scan(email)
                for r in results:
                    db.add_finding(
                        scan_id, profile_name, r.scanner, r.site_name,
                        r.site_url, r.data_type, r.details, r.confidence,
                    )
                db.complete_scan(scan_id, len(results))
                if scanner.name == "hibp":
                    breaches = [r for r in results if r.data_type == "breach"]
                    pastes = [r for r in results if r.data_type == "paste"]
                    parts = []
                    if breaches:
                        parts.append(f"{len(breaches)} breaches")
                    if pastes:
                        parts.append(f"{len(pastes)} pastes")
                    if parts:
                        console.print(f"[red]{', '.join(parts)} found[/red]")
                    else:
                        console.print("[green]no breaches found[/green]")
                else:
                    console.print(f"[green]{len(results)} services found[/green]")
                total_results += len(results)
            except Exception as e:
                db.fail_scan(scan_id, str(e))
                console.print(f"[red]failed: {e}[/red]")

    console.print(f"\n[bold]Total: {total_results} exposures found.[/bold]")


@scan.command("phone")
@click.argument("phones", nargs=-1, required=True)
@click.pass_context
def scan_phone(ctx, phones):
    """Gather information about phone numbers (PhoneInfoga)."""
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"] or "cli"

    from src.scanners.phoneinfoga_scanner import PhoneInfogaScanner

    scanner = PhoneInfogaScanner()
    if not scanner.is_available():
        console.print("[red]PhoneInfoga not available. Run install.sh first.[/red]")
        return

    for phone in phones:
        stripped = phone.strip().lstrip("+")
        if not stripped or not stripped.replace("-", "").replace(" ", "").replace("(", "").replace(")", "").isdigit():
            click.echo(f"Warning: Skipping invalid phone number: {phone}", err=True)
            continue
        console.print(f"\n[bold]Scanning phone: {phone}[/bold]")
        scan_id = db.create_scan(profile_name, "phoneinfoga", "phone", phone)
        try:
            results = scanner.scan(phone)
            for r in results:
                db.add_finding(
                    scan_id, profile_name, r.scanner, r.site_name,
                    r.site_url, r.data_type, r.details, r.confidence,
                )
            db.complete_scan(scan_id, len(results))
            if results:
                console.print(f"  [green]Info gathered[/green]")
                for r in results:
                    if r.details:
                        for k, v in r.details.items():
                            if k != "raw":
                                console.print(f"    {k}: {v}")
            else:
                console.print("  [yellow]No info found[/yellow]")
        except Exception as e:
            db.fail_scan(scan_id, str(e))
            console.print(f"  [red]failed: {e}[/red]")


@scan.command("people")
@click.argument("query")
@click.option("--type", "-t", "query_type", type=click.Choice(["name", "phone", "email", "address"]), default="name",
              help="Search type: 'name' (First Last State), 'phone', 'email', or 'address' (street|city|state|zip)")
@click.pass_context
def scan_people(ctx, query, query_type):
    """Search people-search/data broker sites for your listings."""
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"] or "cli"

    from src.scanners.people_search_scanner import PeopleSearchScanner

    scanner = PeopleSearchScanner()
    if not scanner.is_available():
        console.print("[red]Playwright not available. Run install.sh first.[/red]")
        return

    if query_type == "address":
        parts = query.split("|")
        if len(parts) < 4:
            click.echo(
                "Error: Address query must be pipe-separated: 'street|city|state|zip' "
                f"(got {len(parts)} part(s), need 4)",
                err=True,
            )
            return

    console.print(f"\n[bold]Searching people-search sites ({query_type}): {query}[/bold]")
    scan_id = db.create_scan(profile_name, "people_search", query_type, query)

    try:
        results = scanner.scan(query, query_type)
        for r in results:
            db.add_finding(
                scan_id, profile_name, r.scanner, r.site_name,
                r.site_url, r.data_type, r.details, r.confidence,
            )
        db.complete_scan(scan_id, len(results))
        if results:
            console.print(f"\n[red bold]Found on {len(results)} site(s):[/red bold]")
            for r in results:
                console.print(f"  [red]{r.site_name}[/red]: {r.site_url}")
        else:
            console.print("\n[green]Not found on any people-search sites.[/green]")
    except Exception as e:
        db.fail_scan(scan_id, str(e))
        console.print(f"[red]Scan failed: {e}[/red]")


@scan.command("full")
@click.pass_context
def scan_full(ctx):
    """Run all scans using profile data."""
    profile_name = ctx.obj["profile_name"]
    if not profile_name:
        console.print("[red]Profile required. Use: privacy-toolkit scan full -p <name>[/red]")
        return

    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        console.print(f"[red]Profile '{profile_name}' not found. Create one first.[/red]")
        return

    console.print(f"\n[bold]Full Scan for profile: {profile_name}[/bold]\n")

    # Username scans
    if profile.usernames:
        console.print("[bold cyan]--- Username Scans ---[/bold cyan]")
        ctx.invoke(scan_username, usernames=tuple(profile.usernames))

    # Email scans
    if profile.email_addresses:
        console.print("\n[bold cyan]--- Email Scans ---[/bold cyan]")
        ctx.invoke(scan_email, emails=tuple(profile.email_addresses))

    # Phone scans
    if profile.phone_numbers:
        console.print("\n[bold cyan]--- Phone Scans ---[/bold cyan]")
        ctx.invoke(scan_phone, phones=tuple(profile.phone_numbers))

    # People-search scans (name + phone + email across data broker sites)
    console.print("\n[bold cyan]--- People Search Scans ---[/bold cyan]")
    from src.scanners.people_search_scanner import PeopleSearchScanner
    ps = PeopleSearchScanner()
    if ps.is_available():
        if profile.first_name and profile.last_name:
            if profile.addresses:
                state = profile.addresses[0].state_abbr or profile.addresses[0].state
            else:
                state = None
            name_query = f"{profile.first_name} {profile.last_name}"
            if state:
                name_query += f" {state}"
            ctx.invoke(scan_people, query=name_query, query_type="name")
        if profile.phone_numbers:
            for phone in profile.phone_numbers:
                ctx.invoke(scan_people, query=phone, query_type="phone")
        if profile.email_addresses:
            for email in profile.email_addresses:
                ctx.invoke(scan_people, query=email, query_type="email")
        if profile.addresses:
            for addr in profile.addresses:
                if addr.street and addr.city and (addr.state_abbr or addr.state):
                    state = addr.state_abbr or addr.state
                    addr_query = f"{addr.street}|{addr.city}|{state}|{addr.zip_code}"
                    ctx.invoke(scan_people, query=addr_query, query_type="address")
    else:
        console.print("[yellow]People-search scanner not available. Skipping.[/yellow]")

    console.print("\n[bold green]Full scan complete.[/bold green]")
    console.print(f"Run [bold]privacy-toolkit report -p {profile_name}[/bold] to view all results.")

    # Send notification if configured
    config = ctx.obj["config"]
    if config.signal.enabled:
        from src.notifications import send_signal
        db = ctx.obj["db"]
        count = db.get_findings_count(profile_name)
        send_signal(
            f"Privacy Toolkit: Full scan complete for {profile_name}. {count} exposures found.",
            config.signal,
        )


@scan.command("spiderfoot")
@click.pass_context
def scan_spiderfoot(ctx):
    """Launch SpiderFoot web UI for comprehensive OSINT."""
    from src.scanners.spiderfoot_scanner import SpiderfootScanner

    sf = SpiderfootScanner()
    if not sf.is_available():
        console.print("[red]SpiderFoot Docker image not found.[/red]")
        console.print("Run: docker pull ghcr.io/smicallef/spiderfoot:latest")
        return

    if sf.is_running():
        console.print(f"[green]SpiderFoot already running at http://localhost:{sf.port}[/green]")
    else:
        console.print("Starting SpiderFoot...", end=" ")
        if sf.start():
            console.print(f"[green]Running at http://localhost:{sf.port}[/green]")
        else:
            console.print("[red]Failed to start.[/red]")


# ============================================================================
# REMOVE COMMANDS
# ============================================================================

@cli.group()
def remove():
    """Submit opt-out and removal requests to data brokers."""
    pass


@remove.command("email-request")
@click.option("--broker", "-b", default=None, help="Broker slug or 'all'")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.pass_context
def remove_email(ctx, broker, dry_run):
    """Send CCPA/GDPR deletion emails to data brokers."""
    profile_name = ctx.obj["profile_name"]
    if not profile_name:
        console.print("[red]Profile required. Use -p <name>[/red]")
        return

    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        console.print(f"[red]Profile '{profile_name}' not found.[/red]")
        return

    if not profile:
        click.echo("Error: Failed to load profile. Cannot send removal requests.", err=True)
        return

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    from src.removers.email_remover import EmailRemover
    remover = EmailRemover(config.smtp, db)

    if broker and broker != "all":
        brokers = []
        try:
            brokers.append(load_broker(broker))
        except FileNotFoundError:
            console.print(f"[red]Broker '{broker}' not found.[/red]")
            return
    else:
        brokers = [b for b in load_all_brokers() if b.email_method]

    if not brokers:
        console.print("[yellow]No brokers with email opt-out found.[/yellow]")
        return

    if dry_run:
        console.print(f"[bold]DRY RUN - Preview of {len(brokers)} email(s)[/bold]\n")

    for b in brokers:
        result = remover.send_removal_request(b, profile, dry_run=dry_run)
        if result.get("success"):
            if dry_run:
                console.print(Panel(
                    f"[bold]To:[/bold] {result['to']}\n"
                    f"[bold]Subject:[/bold] {result['subject']}\n"
                    f"[bold]Preview:[/bold]\n{result.get('full_body', result['body_preview'])}",
                    title=f"{b.name}",
                    border_style="blue",
                ))
            else:
                console.print(f"  [green]Sent to {b.name}[/green] ({result['to']})")
        else:
            console.print(f"  [red]{b.name}: {result.get('error', 'failed')}[/red]")

    if not dry_run and brokers:
        console.print(f"\n[bold green]Sent {len(brokers)} removal request(s).[/bold green]")
        console.print("Track status with: [bold]privacy-toolkit track status[/bold]")


@remove.command("form-request")
@click.option("--broker", "-b", required=True, help="Broker slug")
@click.option("--headed", is_flag=True, help="Show browser window")
@click.pass_context
def remove_form(ctx, broker, headed):
    """Automate opt-out web forms via browser (Playwright)."""
    profile_name = ctx.obj["profile_name"]
    if not profile_name:
        console.print("[red]Profile required. Use -p <name>[/red]")
        return

    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        console.print(f"[red]Profile '{profile_name}' not found.[/red]")
        return

    try:
        broker_obj = load_broker(broker)
    except FileNotFoundError:
        console.print(f"[red]Broker '{broker}' not found.[/red]")
        return

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    from src.removers.form_remover import FormRemover
    remover = FormRemover(config.browser, db)

    console.print(f"[bold]Submitting form opt-out for {broker_obj.name}...[/bold]")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            remover.submit_opt_out(broker_obj, profile, headless=not headed)
        )
    finally:
        loop.close()

    if result.get("success"):
        console.print(f"[green]Form submitted for {broker_obj.name}[/green]")
        if result.get("screenshot"):
            console.print(f"  Screenshot: {result['screenshot']}")
    else:
        console.print(f"[red]Failed: {result.get('error', 'unknown')}[/red]")


@remove.command("manual")
@click.pass_context
def remove_manual(ctx):
    """Show manual opt-out instructions for brokers requiring human action."""
    brokers = load_all_brokers()
    from src.removers.manual_remover import show_manual_instructions
    show_manual_instructions(brokers, console)


# ============================================================================
# TRACK COMMANDS
# ============================================================================

@cli.group()
def track():
    """View and manage removal request tracking."""
    pass


@track.command("status")
@click.pass_context
def track_status(ctx):
    """Show status of all removal requests."""
    from src.reporting.terminal import show_removal_status
    show_removal_status(ctx.obj["db"], ctx.obj["profile_name"], console)


@track.command("pending")
@click.pass_context
def track_pending(ctx):
    """Show requests that need follow-up."""
    from src.reporting.terminal import show_pending_rechecks
    show_pending_rechecks(ctx.obj["db"], ctx.obj["profile_name"], console)


@track.command("history")
@click.pass_context
def track_history(ctx):
    """Show scan history."""
    from src.reporting.terminal import show_scan_history
    show_scan_history(ctx.obj["db"], ctx.obj["profile_name"], console)


@track.command("confirm")
@click.argument("removal_id", type=int)
@click.pass_context
def track_confirm(ctx, removal_id):
    """Confirm a removal request was processed."""
    db = ctx.obj["db"]
    db.update_removal_status(removal_id, "confirmed")
    console.print(f"[green]Removal #{removal_id} marked as confirmed.[/green]")


@track.command("reappeared")
@click.argument("removal_id", type=int)
@click.pass_context
def track_reappeared(ctx, removal_id):
    """Mark a removal as reappeared (data came back)."""
    db = ctx.obj["db"]
    db.update_removal_status(removal_id, "reappeared")
    console.print(f"[yellow]Removal #{removal_id} marked as reappeared. Re-submit removal.[/yellow]")


# ============================================================================
# REPORT COMMAND
# ============================================================================

@cli.command("report")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.option("--output", "-o", default=None, help="Output file path (for json)")
@click.pass_context
def report(ctx, fmt, output):
    """Generate exposure report from scan results."""
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"]

    if fmt == "table":
        from src.reporting.terminal import show_scan_results
        show_scan_results(db, profile_name, console)
    elif fmt == "json":
        from src.reporting.json_export import export_findings
        path = export_findings(db, profile_name, output)
        console.print(f"[green]Exported to: {path}[/green]")


# ============================================================================
# PROFILE COMMANDS
# ============================================================================

@cli.group()
def profile():
    """Manage user profiles."""
    pass


@profile.command("create")
@click.argument("name")
def profile_create(name):
    """Create a new user profile interactively."""
    path = PROFILES_DIR / f"{name}.yaml"
    if path.exists():
        console.print(f"[yellow]Profile '{name}' already exists. Edit {path}[/yellow]")
        return

    console.print(f"[bold]Creating profile: {name}[/bold]\n")

    first = click.prompt("First name", default="")
    last = click.prompt("Last name", default="")
    full = click.prompt("Full name", default=f"{first} {last}".strip())

    emails = []
    while True:
        email = click.prompt("Email address (blank to stop)", default="")
        if not email:
            break
        emails.append(email)

    phones = []
    while True:
        phone = click.prompt("Phone number with country code (blank to stop)", default="")
        if not phone:
            break
        phones.append(phone)

    usernames = []
    while True:
        uname = click.prompt("Username to search (blank to stop)", default="")
        if not uname:
            break
        usernames.append(uname)

    p = Profile(
        name=name,
        first_name=first,
        last_name=last,
        full_name=full,
        email_addresses=emails,
        phone_numbers=phones,
        usernames=usernames,
    )
    p.to_yaml(path)
    console.print(f"\n[green]Profile saved to {path}[/green]")
    console.print(f"Run: [bold]privacy-toolkit scan full -p {name}[/bold]")


@profile.command("list")
def profile_list():
    """List available profiles."""
    profiles = list_profiles()
    if not profiles:
        console.print("[yellow]No profiles found. Create one with: privacy-toolkit profile create <name>[/yellow]")
        return
    console.print("[bold]Profiles:[/bold]")
    for p in profiles:
        console.print(f"  - {p}")


@profile.command("show")
@click.argument("name")
def profile_show(name):
    """Display profile details."""
    try:
        p = load_profile(name)
    except FileNotFoundError:
        console.print(f"[red]Profile '{name}' not found.[/red]")
        return

    table = Table(title=f"Profile: {name}")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Full Name", p.full_name)
    table.add_row("First Name", p.first_name)
    table.add_row("Last Name", p.last_name)
    table.add_row("Emails", ", ".join(p.email_addresses) or "(none)")
    table.add_row("Phones", ", ".join(p.phone_numbers) or "(none)")
    table.add_row("Usernames", ", ".join(p.usernames) or "(none)")
    table.add_row("Addresses", "; ".join(a.formatted for a in p.addresses) or "(none)")
    table.add_row("Jurisdiction", p.jurisdiction)
    table.add_row("Laws", ", ".join(p.applicable_laws))
    console.print(table)


# ============================================================================
# SCHEDULE COMMANDS
# ============================================================================

@cli.group()
def schedule():
    """Manage periodic re-scan scheduling."""
    pass


@schedule.command("enable")
@click.pass_context
def schedule_enable(ctx):
    """Install cron jobs for periodic re-scans."""
    profile_name = ctx.obj["profile_name"]
    if not profile_name:
        console.print("[red]Profile required. Use -p <name>[/red]")
        return

    from src.scheduler import install_cron
    config = ctx.obj["config"]

    if install_cron(profile_name, config.schedule):
        console.print(f"[green]Cron jobs installed for profile '{profile_name}'.[/green]")
        console.print(f"  Re-scan: {config.schedule.cron_time}")
        console.print(f"  Follow-up check: daily at 9 AM")
    else:
        console.print("[red]Failed to install cron jobs.[/red]")


@schedule.command("disable")
def schedule_disable():
    """Remove privacy toolkit cron jobs."""
    from src.scheduler import remove_cron
    if remove_cron():
        console.print("[green]Cron jobs removed.[/green]")
    else:
        console.print("[red]Failed to remove cron jobs.[/red]")


@schedule.command("status")
def schedule_status():
    """Show current schedule status."""
    from src.scheduler import get_cron_status
    status = get_cron_status()
    if status["installed"]:
        console.print("[green]Scheduled jobs active:[/green]")
        for line in status["lines"]:
            console.print(f"  {line}")
    else:
        console.print("[yellow]No scheduled jobs. Run: privacy-toolkit schedule enable -p <name>[/yellow]")


# ============================================================================
# BROKERS COMMAND
# ============================================================================

@cli.command("brokers")
@click.option("--priority", "-P", type=click.Choice(["critical", "high", "medium", "low"]), default=None)
def brokers_list(priority):
    """List all configured data brokers."""
    brokers = load_all_brokers()
    if priority:
        brokers = [b for b in brokers if b.priority.value == priority]

    if not brokers:
        console.print("[yellow]No brokers found.[/yellow]")
        return

    table = Table(title=f"Data Brokers ({len(brokers)})")
    table.add_column("Slug", style="bold", width=25)
    table.add_column("Name", width=25)
    table.add_column("Priority", width=10)
    table.add_column("Methods", width=20)
    table.add_column("Category", width=18)

    priority_colors = {
        "critical": "red bold",
        "high": "red",
        "medium": "yellow",
        "low": "dim",
    }

    for b in sorted(brokers, key=lambda x: ["critical", "high", "medium", "low"].index(x.priority.value)):
        methods = ", ".join(m.type.value for m in b.methods)
        color = priority_colors.get(b.priority.value, "")
        table.add_row(
            b.slug,
            b.name,
            f"[{color}]{b.priority.value}[/{color}]",
            methods,
            b.category,
        )

    console.print(table)


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
