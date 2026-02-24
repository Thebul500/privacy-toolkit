"""Privacy Toolkit CLI - Discover, remove, and track personal data exposure."""

from __future__ import annotations
import asyncio
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.text import Text

from src.config import (
    BROKERS_DIR, Config, PROFILES_DIR, TOOLKIT_DIR,
    load_all_brokers, load_broker, load_profile, list_profiles,
    validate_broker,
)
from src.db import Database
from src.models import Profile

logger = logging.getLogger(__name__)

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
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Running {scanners[0].name}...", total=None)
            for scanner in scanners:
                progress.update(task, description=f"Running {scanner.name}...")
                scan_id = db.create_scan(profile_name, scanner.name, "username", username)
                try:
                    results = scanner.scan(username)
                    for r in results:
                        db.add_finding(
                            scan_id, profile_name, r.scanner, r.site_name,
                            r.site_url, r.data_type, r.details, r.confidence,
                        )
                    db.complete_scan(scan_id, len(results))
                    total_results += len(results)
                except Exception as e:
                    db.fail_scan(scan_id, str(e))
                    click.echo(f"  {scanner.name} failed: {e}", err=True)
            progress.update(task, description=f"Complete: {total_results} accounts found")

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
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Running {scanners[0].name}...", total=None)
            for scanner in scanners:
                progress.update(task, description=f"Running {scanner.name}...")
                scan_id = db.create_scan(profile_name, scanner.name, "email", email)
                try:
                    results = scanner.scan(email)
                    for r in results:
                        db.add_finding(
                            scan_id, profile_name, r.scanner, r.site_name,
                            r.site_url, r.data_type, r.details, r.confidence,
                        )
                    db.complete_scan(scan_id, len(results))
                    total_results += len(results)
                except Exception as e:
                    db.fail_scan(scan_id, str(e))
                    click.echo(f"  {scanner.name} failed: {e}", err=True)
            progress.update(task, description=f"Complete: {total_results} exposures found")

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
                console.print("  [green]Info gathered[/green]")
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

    config = ctx.obj["config"]
    scanner = PeopleSearchScanner(rate_limit_delay=config.browser.rate_limit_delay)
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
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Checking data broker sites...", total=None)
            results = scanner.scan(query, query_type)
            progress.update(task, description=f"Found {len(results)} results")
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

    # Determine which scanners will actually run
    from src.scanners.people_search_scanner import PeopleSearchScanner
    config = ctx.obj["config"]
    ps = PeopleSearchScanner(rate_limit_delay=config.browser.rate_limit_delay)
    ps_available = ps.is_available()

    scanner_count = 0
    if profile.usernames:
        scanner_count += 1
    if profile.email_addresses:
        scanner_count += 1
    if profile.phone_numbers:
        scanner_count += 1
    if ps_available:
        scanner_count += 1

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        overall = progress.add_task("Full scan", total=scanner_count)

        # Username scans
        if profile.usernames:
            progress.update(overall, description="Scanning usernames (Sherlock + Maigret)...")
            ctx.invoke(scan_username, usernames=tuple(profile.usernames))
            progress.advance(overall)

        # Email scans
        if profile.email_addresses:
            progress.update(overall, description="Scanning emails (Holehe + HIBP)...")
            ctx.invoke(scan_email, emails=tuple(profile.email_addresses))
            progress.advance(overall)

        # Phone scans
        if profile.phone_numbers:
            progress.update(overall, description="Scanning phone numbers (PhoneInfoga)...")
            ctx.invoke(scan_phone, phones=tuple(profile.phone_numbers))
            progress.advance(overall)

        # People-search scans (name + phone + email across data broker sites)
        if ps_available:
            progress.update(overall, description="Scanning people-search sites...")
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
            progress.advance(overall)
        else:
            console.print("[yellow]People-search scanner not available. Skipping.[/yellow]")

        progress.update(overall, description="Full scan complete")

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
# ACCOUNTS COMMANDS
# ============================================================================

@cli.group()
def accounts():
    """Discover accounts, breaches, and exposures with interactive removal guidance."""
    pass


@accounts.command("find-by-email")
@click.argument("email")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
@click.pass_context
def accounts_find_by_email(ctx, email, config_path):
    """Find accounts and breaches linked to an email address."""
    if "@" not in email:
        console.print(f"[red]Invalid email address: {email}[/red]")
        return

    config = ctx.obj["config"]
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"] or "cli"

    all_results = []

    from src.scanners.holehe_scanner import HoleheScanner
    from src.scanners.hibp_scanner import HIBPScanner

    holehe = HoleheScanner()
    holehe_available = holehe.is_available()
    if not holehe_available:
        console.print("[yellow]Holehe not available. Skipping account discovery.[/yellow]")

    hibp_key = getattr(config, "hibp_api_key", "")
    hibp = HIBPScanner(api_key=hibp_key)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking registered accounts...", total=None)

        # --- Holehe: find registered accounts ---
        if holehe_available:
            progress.update(task, description="Checking registered accounts (Holehe)...")
            scan_id = db.create_scan(profile_name, holehe.name, "email", email)
            try:
                results = holehe.scan(email)
                for r in results:
                    db.add_finding(
                        scan_id, profile_name, r.scanner, r.site_name,
                        r.site_url, r.data_type, r.details, r.confidence,
                    )
                db.complete_scan(scan_id, len(results))
                all_results.extend(results)
            except Exception as e:
                db.fail_scan(scan_id, str(e))
                click.echo(f"  Holehe failed: {e}", err=True)
                logger.error("Holehe scan failed for %s: %s", email, e)

        # --- HIBP: find breaches and pastes ---
        progress.update(task, description="Scanning breaches and paste dumps (HIBP)...")
        scan_id = db.create_scan(profile_name, hibp.name, "email", email)
        try:
            results = hibp.scan(email)
            for r in results:
                db.add_finding(
                    scan_id, profile_name, r.scanner, r.site_name,
                    r.site_url, r.data_type, r.details, r.confidence,
                )
            db.complete_scan(scan_id, len(results))
            all_results.extend(results)
        except Exception as e:
            db.fail_scan(scan_id, str(e))
            click.echo(f"  HIBP failed: {e}", err=True)
            logger.error("HIBP scan failed for %s: %s", email, e)

        progress.update(task, description=f"Complete: {len(all_results)} results found")

    if not all_results:
        console.print(f"\n[green]No accounts or breaches found for {email}.[/green]")
        return

    # --- Build combined results table ---
    table = Table(title=f"Account & Breach Discovery: {email}")
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Service/Breach", style="bold", min_width=20)
    table.add_column("Type", width=12)
    table.add_column("Data Exposed", min_width=25)
    table.add_column("Action", style="cyan", min_width=18)

    for idx, r in enumerate(all_results, 1):
        # Determine type label
        if r.data_type == "email_registered":
            type_label = "account"
        elif r.data_type == "breach":
            type_label = "breach"
        elif r.data_type == "paste":
            type_label = "paste"
        else:
            type_label = r.data_type

        # Determine data exposed
        if r.data_type == "breach":
            data_classes = r.details.get("data_classes", [])
            data_exposed = ", ".join(data_classes[:5])
            if len(data_classes) > 5:
                data_exposed += f" (+{len(data_classes) - 5} more)"
        elif r.data_type == "paste":
            data_exposed = f"Source: {r.details.get('source', 'Unknown')}"
            if r.details.get("email_count"):
                data_exposed += f" ({r.details['email_count']} emails)"
        elif r.data_type == "email_registered":
            parts = []
            if r.details.get("emailrecovery"):
                parts.append(f"Recovery: {r.details['emailrecovery']}")
            if r.details.get("phoneNumber"):
                parts.append(f"Phone: {r.details['phoneNumber']}")
            data_exposed = ", ".join(parts) if parts else "Email registered"
        else:
            data_exposed = str(r.details) if r.details else ""

        # Determine action
        if r.data_type == "email_registered":
            action = "Delete account"
        elif r.data_type == "breach":
            action = "Change password"
        elif r.data_type == "paste":
            action = "Monitor"
        else:
            action = "Review"

        # Color the type label
        if type_label == "account":
            type_styled = f"[blue]{type_label}[/blue]"
        elif type_label == "breach":
            type_styled = f"[red]{type_label}[/red]"
        elif type_label == "paste":
            type_styled = f"[yellow]{type_label}[/yellow]"
        else:
            type_styled = type_label

        table.add_row(str(idx), r.site_name, type_styled, data_exposed, action)

    console.print()
    console.print(table)
    console.print(f"\n[bold]Total: {len(all_results)} result(s) for {email}[/bold]")

    # --- Interactive removal guidance ---
    account_results = [r for r in all_results if r.data_type == "email_registered"]
    breach_results = [r for r in all_results if r.data_type == "breach"]

    if account_results or breach_results:
        if click.confirm("\nWould you like removal guidance for these accounts?"):
            console.print()
            if account_results:
                console.print(Panel("[bold]Account Deletion Guidance[/bold]", border_style="blue"))
                for r in account_results:
                    service = r.site_name
                    domain = r.site_url
                    if domain and not domain.startswith("http"):
                        domain = f"https://{domain}"
                    if domain:
                        console.print(f"  [bold]{service}[/bold]: Visit {domain}/account/delete or {domain}/settings to delete your account")
                    else:
                        console.print(f"  [bold]{service}[/bold]: See guides/{service.lower()}.yaml for step-by-step instructions")
            if breach_results:
                console.print()
                console.print(Panel("[bold]Breach Response Guidance[/bold]", border_style="red"))
                for r in breach_results:
                    breach_name = r.site_name
                    data_classes = r.details.get("data_classes", [])
                    console.print(f"  [bold]{breach_name}[/bold]: Change your password immediately")
                    if "Passwords" in data_classes:
                        console.print("    [red]Passwords were exposed[/red] - change on ALL sites where you reused this password")
                    if data_classes:
                        console.print(f"    Compromised data: {', '.join(data_classes)}")


@accounts.command("find-by-phone")
@click.argument("phone")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
@click.pass_context
def accounts_find_by_phone(ctx, phone, config_path):
    """Find services and information linked to a phone number."""
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"] or "cli"

    from src.scanners.phoneinfoga_scanner import PhoneInfogaScanner

    scanner = PhoneInfogaScanner()
    if not scanner.is_available():
        console.print("[red]PhoneInfoga not available. Run install.sh first.[/red]")
        return

    scan_id = db.create_scan(profile_name, "phoneinfoga", "phone", phone)

    all_results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Scanning phone number: {phone}...", total=None)
        try:
            results = scanner.scan(phone)
            for r in results:
                db.add_finding(
                    scan_id, profile_name, r.scanner, r.site_name,
                    r.site_url, r.data_type, r.details, r.confidence,
                )
            db.complete_scan(scan_id, len(results))
            all_results.extend(results)
        except Exception as e:
            db.fail_scan(scan_id, str(e))
            click.echo(f"  PhoneInfoga failed: {e}", err=True)
            logger.error("PhoneInfoga scan failed for %s: %s", phone, e)
        progress.update(task, description=f"Complete: {len(all_results)} results found")

    if not all_results:
        console.print(f"\n[green]No information found for {phone}.[/green]")
        return

    # --- Build results table ---
    table = Table(title=f"Phone Number Discovery: {phone}")
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Service/Source", style="bold", min_width=20)
    table.add_column("Type", width=12)
    table.add_column("Details", min_width=30)
    table.add_column("Action", style="cyan", min_width=18)

    for idx, r in enumerate(all_results, 1):
        type_label = r.data_type if r.data_type else "phone_info"

        # Build details string from the details dict
        detail_parts = []
        if r.details:
            for k, v in r.details.items():
                if k == "raw" and isinstance(v, dict):
                    for rk, rv in v.items():
                        if rv:
                            detail_parts.append(f"{rk}: {rv}")
                elif k != "raw" and v:
                    detail_parts.append(f"{k}: {v}")
        details_str = ", ".join(detail_parts[:6])
        if len(detail_parts) > 6:
            details_str += f" (+{len(detail_parts) - 6} more)"

        action = "Review exposure"

        table.add_row(str(idx), r.site_name, type_label, details_str, action)

    console.print()
    console.print(table)
    console.print(f"\n[bold]Total: {len(all_results)} result(s) for {phone}[/bold]")

    # --- Interactive removal guidance ---
    if all_results:
        if click.confirm("\nWould you like removal guidance for these findings?"):
            console.print()
            console.print(Panel("[bold]Phone Number Removal Guidance[/bold]", border_style="blue"))
            for r in all_results:
                service = r.site_name
                if r.site_url:
                    console.print(f"  [bold]{service}[/bold]: Visit {r.site_url} to manage your phone number settings")
                else:
                    console.print(f"  [bold]{service}[/bold]: See guides/{service.lower()}.yaml for step-by-step instructions")
            console.print()
            console.print("  [dim]Tip: Contact your carrier to request unlisted status for your number.[/dim]")


@accounts.command("find-by-username")
@click.argument("username")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
@click.pass_context
def accounts_find_by_username(ctx, username, config_path):
    """Find accounts linked to a username across social networks and websites."""
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"] or "cli"

    from src.scanners.sherlock_scanner import SherlockScanner
    from src.scanners.maigret_scanner import MaigretScanner

    scanners_available = []
    sherlock = SherlockScanner()
    maigret = MaigretScanner()

    if sherlock.is_available():
        scanners_available.append(sherlock)
    else:
        console.print("[yellow]Sherlock not available. Skipping.[/yellow]")

    if maigret.is_available():
        scanners_available.append(maigret)
    else:
        console.print("[yellow]Maigret not available. Skipping.[/yellow]")

    if not scanners_available:
        console.print("[red]No username scanners available. Run install.sh first.[/red]")
        return

    # Collect results from all scanners
    sherlock_results = []
    maigret_results = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Running {scanners_available[0].name}...", total=None)
        for scanner in scanners_available:
            progress.update(task, description=f"Running {scanner.name}...")
            scan_id = db.create_scan(profile_name, scanner.name, "username", username)
            try:
                results = scanner.scan(username)
                for r in results:
                    db.add_finding(
                        scan_id, profile_name, r.scanner, r.site_name,
                        r.site_url, r.data_type, r.details, r.confidence,
                    )
                db.complete_scan(scan_id, len(results))
                if scanner.name == "sherlock":
                    sherlock_results = results
                elif scanner.name == "maigret":
                    maigret_results = results
            except Exception as e:
                db.fail_scan(scan_id, str(e))
                click.echo(f"  {scanner.name} failed: {e}", err=True)
                logger.error("%s scan failed for %s: %s", scanner.name, username, e)
        total_found = len(sherlock_results) + len(maigret_results)
        progress.update(task, description=f"Complete: {total_found} accounts found")

    # --- Deduplicate: prefer Maigret results when both find the same site ---
    maigret_sites = {r.site_name.lower(): r for r in maigret_results}
    deduplicated = list(maigret_results)  # start with all maigret results
    for r in sherlock_results:
        if r.site_name.lower() not in maigret_sites:
            deduplicated.append(r)

    if not deduplicated:
        console.print(f"\n[green]No accounts found for username: {username}[/green]")
        return

    # --- Build results table ---
    table = Table(title=f"Username Discovery: {username}")
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Site", style="bold", min_width=20)
    table.add_column("URL", min_width=35)
    table.add_column("Confidence", width=12)
    table.add_column("Action", style="cyan", min_width=15)

    for idx, r in enumerate(deduplicated, 1):
        confidence = r.confidence or "medium"
        if confidence == "high":
            conf_styled = f"[green]{confidence}[/green]"
        elif confidence == "medium":
            conf_styled = f"[yellow]{confidence}[/yellow]"
        else:
            conf_styled = f"[dim]{confidence}[/dim]"

        url = r.site_url or ""
        action = "Delete account"

        table.add_row(str(idx), r.site_name, url, conf_styled, action)

    console.print()
    console.print(table)
    console.print(f"\n[bold]Total: {len(deduplicated)} unique site(s) for username: {username}[/bold]")
    if sherlock_results and maigret_results:
        overlap = len(sherlock_results) + len(maigret_results) - len(deduplicated)
        if overlap > 0:
            console.print(f"  [dim]({overlap} duplicate(s) removed across Sherlock and Maigret)[/dim]")

    # --- Interactive removal guidance ---
    if click.confirm("\nWould you like removal guidance for these accounts?"):
        console.print()
        console.print(Panel("[bold]Account Deletion Guidance[/bold]", border_style="blue"))
        for r in deduplicated:
            site = r.site_name
            url = r.site_url or ""
            if url:
                # Try to construct a settings/delete URL from the profile URL
                console.print(f"  [bold]{site}[/bold]: Visit {url} to manage your account")
            else:
                console.print(f"  [bold]{site}[/bold]: See guides/{site.lower()}.yaml for step-by-step instructions")


@accounts.command("exposure-report")
@click.option("--profile", "-p", "profile_name", required=True, help="Profile name")
@click.option("--config", "-c", "config_path", default=None, help="Config file path")
@click.pass_context
def accounts_exposure_report(ctx, profile_name, config_path):
    """Generate a breach exposure summary report for a profile."""
    config = ctx.obj["config"]
    db = ctx.obj["db"]

    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        console.print(f"[red]Profile '{profile_name}' not found. Create one first.[/red]")
        return

    if not profile.email_addresses:
        console.print(f"[red]Profile '{profile_name}' has no email addresses configured.[/red]")
        return

    from src.scanners.hibp_scanner import HIBPScanner

    hibp_key = getattr(config, "hibp_api_key", "")
    hibp = HIBPScanner(api_key=hibp_key)

    all_breaches = []  # list of (email, ScanResult)
    email_count = len(profile.email_addresses)

    console.print(Panel(
        f"[bold]Breach Exposure Report[/bold]\n"
        f"Profile: {profile_name}\n"
        f"Emails: {email_count}",
        border_style="blue",
    ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Checking breaches", total=email_count)
        for email in profile.email_addresses:
            progress.update(task, description=f"Checking {email}...")
            scan_id = db.create_scan(profile_name, hibp.name, "email", email)
            try:
                results = hibp.scan(email)
                for r in results:
                    db.add_finding(
                        scan_id, profile_name, r.scanner, r.site_name,
                        r.site_url, r.data_type, r.details, r.confidence,
                    )
                db.complete_scan(scan_id, len(results))
                breaches = [r for r in results if r.data_type == "breach"]
                for b in breaches:
                    all_breaches.append((email, b))
            except Exception as e:
                db.fail_scan(scan_id, str(e))
                click.echo(f"  {email}: scan failed - {e}", err=True)
                logger.error("HIBP scan failed for %s: %s", email, e)
            progress.advance(task)
        progress.update(task, description=f"Complete: {len(all_breaches)} breaches found")

    if not all_breaches:
        console.print()
        console.print(Panel(
            "[bold green]No breaches found![/bold green]\n"
            f"All {email_count} email address(es) are clean.",
            border_style="green",
            title="Exposure Summary",
        ))
        return

    # --- Aggregate breach data ---
    # Group by breach name, collect affected emails and data types
    breach_map = {}  # breach_name -> {date, data_classes, emails}
    all_data_classes = set()

    for email, b in all_breaches:
        name = b.site_name
        if name not in breach_map:
            breach_map[name] = {
                "date": b.details.get("breach_date", "Unknown"),
                "data_classes": b.details.get("data_classes", []),
                "emails": set(),
            }
        breach_map[name]["emails"].add(email)
        all_data_classes.update(b.details.get("data_classes", []))

    # --- Risk assessment ---
    high_risk_types = {"Passwords", "Password hints", "Social security numbers", "Credit cards",
                       "Bank account numbers", "Financial data", "Credit card CVV",
                       "Partial credit card data", "PINs"}
    medium_risk_types = {"Email addresses", "Phone numbers", "Physical addresses",
                         "Dates of birth", "IP addresses", "Genders"}

    exposed_high = all_data_classes & high_risk_types
    exposed_medium = all_data_classes & medium_risk_types

    if exposed_high:
        risk_level = "HIGH"
        risk_color = "red bold"
        risk_detail = f"Sensitive data exposed: {', '.join(sorted(exposed_high))}"
    elif exposed_medium:
        risk_level = "MEDIUM"
        risk_color = "yellow bold"
        risk_detail = f"Personal data exposed: {', '.join(sorted(exposed_medium))}"
    else:
        risk_level = "LOW"
        risk_color = "green bold"
        risk_detail = "Only non-sensitive data types exposed"

    # --- Summary panel ---
    console.print()
    console.print(Panel(
        f"[bold]Total breaches found:[/bold] {len(breach_map)}\n"
        f"[bold]Emails affected:[/bold] {len(set(e for e, _ in all_breaches))}/{email_count}\n"
        f"[bold]Risk assessment:[/bold] [{risk_color}]{risk_level}[/{risk_color}]\n"
        f"  {risk_detail}",
        title="Exposure Summary",
        border_style="red" if risk_level == "HIGH" else ("yellow" if risk_level == "MEDIUM" else "green"),
    ))

    # --- Breach details table ---
    table = Table(title="Breach Details")
    table.add_column("Breach Name", style="bold", min_width=22)
    table.add_column("Date", width=12)
    table.add_column("Data Types Compromised", min_width=35)
    table.add_column("Emails Affected", min_width=20)

    for name in sorted(breach_map.keys()):
        info = breach_map[name]
        data_types = ", ".join(info["data_classes"][:6])
        if len(info["data_classes"]) > 6:
            data_types += f" (+{len(info['data_classes']) - 6} more)"
        emails = ", ".join(sorted(info["emails"]))
        table.add_row(name, info["date"], data_types, emails)

    console.print()
    console.print(table)

    # --- Recommendations ---
    console.print()
    recommendations = []
    if "Passwords" in all_data_classes:
        recommendations.append("[red]URGENT:[/red] Change passwords on all breached services and any site where you reused them")
    if "Email addresses" in all_data_classes:
        recommendations.append("Enable 2FA/MFA on all breached accounts")
    if "Phone numbers" in all_data_classes:
        recommendations.append("Watch for SIM-swap attacks; contact your carrier about port-out protection")
    if "Social security numbers" in all_data_classes:
        recommendations.append("[red]URGENT:[/red] Place a credit freeze at all three credit bureaus (Equifax, Experian, TransUnion)")
    if not recommendations:
        recommendations.append("Continue monitoring for new breaches with periodic scans")

    console.print(Panel(
        "\n".join(f"  {i+1}. {rec}" for i, rec in enumerate(recommendations)),
        title="Recommendations",
        border_style="cyan",
    ))


# ============================================================================
# REMOVE COMMANDS
# ============================================================================

@cli.group()
def remove():
    """Submit opt-out and removal requests to data brokers."""
    pass


@remove.command("email-request")
@click.option("--broker", "-b", "broker_input", multiple=True,
              help="Broker slug(s). Repeat or comma-separate: -b a,b -b c. Default: all")
@click.option("--dry-run", is_flag=True, help="Preview without sending")
@click.pass_context
def remove_email(ctx, broker_input, dry_run):
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

    # Parse broker slugs: split each input by comma, flatten
    slugs = []
    for item in broker_input:
        for part in item.split(","):
            part = part.strip()
            if part:
                slugs.append(part)

    if not slugs or slugs == ["all"]:
        brokers = [b for b in load_all_brokers() if b.email_method]
    else:
        brokers = []
        for slug in slugs:
            try:
                b = load_broker(slug)
            except FileNotFoundError:
                console.print(f"[yellow]Broker '{slug}' not found, skipping.[/yellow]")
                continue
            if not b.email_method:
                console.print(f"[yellow]Broker '{slug}' has no email method, skipping.[/yellow]")
                continue
            brokers.append(b)

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
@click.option("--dry-run", is_flag=True, help="Preview form steps without submitting")
@click.pass_context
def remove_form(ctx, broker, headed, dry_run):
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

    if dry_run:
        console.print(f"[bold]DRY RUN - Previewing form opt-out for {broker_obj.name}...[/bold]")
    else:
        console.print(f"[bold]Submitting form opt-out for {broker_obj.name}...[/bold]")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(
            remover.submit_opt_out(broker_obj, profile, headless=not headed, dry_run=dry_run)
        )
    finally:
        loop.close()

    if result.get("success"):
        if dry_run:
            console.print(f"\n[bold]Steps that would be executed for {broker_obj.name}:[/bold]")
            for step_desc in result.get("steps", []):
                console.print(f"  {step_desc}")
            if result.get("screenshot"):
                console.print(f"\n  Screenshot: {result['screenshot']}")
        else:
            console.print(f"[green]Form submitted for {broker_obj.name}[/green]")
            if result.get("screenshot"):
                console.print(f"  Screenshot: {result['screenshot']}")
    else:
        console.print(f"[red]Failed: {result.get('error', 'unknown')}[/red]")


@remove.command("follow-up")
@click.option("--dry-run", is_flag=True, help="List overdue brokers without sending emails")
@click.option("--days", default=None, type=int, help="Override expected_days threshold for all brokers")
@click.pass_context
def remove_follow_up(ctx, dry_run, days):
    """Send follow-up emails for overdue removal requests."""
    profile_name = ctx.obj["profile_name"]
    if not profile_name:
        console.print("[red]Profile required. Use -p <name>[/red]")
        return

    try:
        profile = load_profile(profile_name)
    except FileNotFoundError:
        console.print(f"[red]Profile '{profile_name}' not found.[/red]")
        return

    config = ctx.obj["config"]
    db = ctx.obj["db"]

    # Query overdue removals
    overdue = db.get_overdue_removals(profile=profile_name, days_threshold=days)

    if not overdue:
        console.print(f"[green]No overdue removal requests found for profile '{profile_name}'.[/green]")
        return

    console.print(f"\n[bold]Found {len(overdue)} overdue removal request(s) for profile '{profile_name}'[/bold]\n")

    if dry_run:
        console.print("[yellow]DRY RUN -- no emails will be sent[/yellow]\n")

    from src.removers.email_remover import EmailRemover
    remover = EmailRemover(config.smtp, db)

    # Build results table
    table = Table(title="Follow-Up Results")
    table.add_column("Broker", style="bold", min_width=20)
    table.add_column("Submitted", width=12)
    table.add_column("Days Overdue", width=14, justify="right")
    table.add_column("Follow-up Status", min_width=18)

    sent_count = 0
    error_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Processing follow-ups...", total=len(overdue))

        for removal in overdue:
            broker_slug = removal["broker_slug"]
            broker_name = removal.get("broker_name", broker_slug)
            submitted_at = removal.get("submitted_at", "")[:10]

            # Calculate days overdue
            days_overdue = 0
            if removal.get("submitted_at"):
                try:
                    submitted_dt = datetime.fromisoformat(removal["submitted_at"])
                    days_overdue = (datetime.now() - submitted_dt).days
                except (ValueError, TypeError):
                    days_overdue = 0

            progress.update(task, description=f"Processing {broker_name}...")

            if dry_run:
                table.add_row(
                    broker_name,
                    submitted_at,
                    str(days_overdue),
                    "[yellow]Would send[/yellow]",
                )
                progress.advance(task)
                continue

            # Load the broker YAML
            try:
                broker = load_broker(broker_slug)
            except FileNotFoundError:
                logger.warning("Broker YAML not found for slug=%s, skipping follow-up", broker_slug)
                table.add_row(
                    broker_name,
                    submitted_at,
                    str(days_overdue),
                    "[red]Broker YAML missing[/red]",
                )
                error_count += 1
                progress.advance(task)
                continue

            if not broker.email_method:
                table.add_row(
                    broker_name,
                    submitted_at,
                    str(days_overdue),
                    "[dim]No email method[/dim]",
                )
                progress.advance(task)
                continue

            # Send the follow-up
            result = remover.send_follow_up(removal, profile, broker)

            if result.get("success"):
                sent_count += 1
                table.add_row(
                    broker_name,
                    submitted_at,
                    str(days_overdue),
                    "[green]Sent[/green]",
                )
            else:
                error_count += 1
                err_msg = result.get("error", "unknown error")
                table.add_row(
                    broker_name,
                    submitted_at,
                    str(days_overdue),
                    f"[red]{err_msg}[/red]",
                )

            progress.advance(task)

    console.print(table)

    if dry_run:
        console.print(f"\n[bold]{len(overdue)} broker(s) would receive follow-up emails.[/bold]")
        console.print("Remove --dry-run to actually send.")
    else:
        console.print(f"\n[bold]Follow-up complete:[/bold] {sent_count} sent, {error_count} failed")


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


@track.command("bounces")
@click.pass_context
def track_bounces(ctx):
    """Check Gmail for bounced email delivery failures and update removal records."""
    from src.removers.email_remover import EmailRemover
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    remover = EmailRemover(config.smtp, db)
    console.print("[blue]Checking Gmail for bounce-back messages...[/blue]")
    bounces = remover.check_bounces()
    if not bounces:
        console.print("[green]No bounced emails found.[/green]")
        return
    console.print(f"\n[yellow]Found {len(bounces)} bounced address(es):[/yellow]")
    for b in bounces:
        console.print(f"  [red]{b['address']}[/red] — {b['error']}")
    console.print("\n[dim]Matching removal requests have been marked as rejected.[/dim]")


@track.command("responses")
@click.pass_context
def track_responses(ctx):
    """Check Gmail for broker replies and classify what action is needed."""
    from src.removers.email_remover import EmailRemover
    config = ctx.obj["config"]
    db = ctx.obj["db"]
    remover = EmailRemover(config.smtp, db)
    console.print("[blue]Checking Gmail for broker responses...[/blue]")
    responses = remover.check_responses()
    if not responses:
        console.print("[green]No broker responses found.[/green]")
        return

    # Group by category
    categories = {
        "needs_form": ("Needs Form/Website Action", "yellow"),
        "needs_verification": ("Needs Identity Verification", "red"),
        "completed": ("Deletion Confirmed", "green"),
        "no_records": ("No Records Found", "cyan"),
        "acknowledged": ("Acknowledged (Waiting)", "dim"),
    }

    grouped: dict[str, list[dict]] = {}
    for r in responses:
        grouped.setdefault(r["category"], []).append(r)

    console.print(f"\n[bold]Found {len(responses)} broker response(s):[/bold]\n")

    for cat_key in ["needs_form", "needs_verification", "completed", "no_records", "acknowledged"]:
        items = grouped.get(cat_key, [])
        if not items:
            continue
        label, color = categories[cat_key]
        console.print(f"[bold {color}]{label} ({len(items)}):[/bold {color}]")
        for r in items:
            broker = r["broker"]
            rid = f" (#{r['removal_id']})" if r["removal_id"] else ""
            console.print(f"  [{color}]{broker}{rid}[/{color}] — {r['from']}")
            if r["detail"]:
                detail = r["detail"][:120]
                console.print(f"    [dim]{detail}[/dim]")
        console.print()

    # Summary
    action_needed = len(grouped.get("needs_form", [])) + len(grouped.get("needs_verification", []))
    if action_needed:
        console.print(f"[bold yellow]{action_needed} response(s) require manual action.[/bold yellow]")


# ============================================================================
# SCORE COMMAND
# ============================================================================

@cli.command("score")
@click.pass_context
def score(ctx):
    """Calculate and display your privacy exposure score."""
    profile_name = ctx.obj["profile_name"]
    if not profile_name:
        console.print("[red]Profile required. Use: privacy-toolkit score -p <name>[/red]")
        return

    db = ctx.obj["db"]

    from src.scoring import calculate_score

    ps = calculate_score(db, profile_name)

    # Color based on grade
    if ps.grade in ("A", "B"):
        score_color = "green"
    elif ps.grade == "C":
        score_color = "yellow"
    else:
        score_color = "red"

    # Build score display
    score_text = Text()
    score_text.append(f"  {ps.score}", style=f"bold {score_color}")
    score_text.append(" / 100  ", style="dim")
    score_text.append("Grade: ", style="bold white")
    score_text.append(f"{ps.grade}", style=f"bold {score_color}")

    console.print()
    console.print(Panel(
        score_text,
        title=f"Privacy Score: {profile_name}",
        border_style=score_color,
        padding=(1, 2),
    ))

    # Stats breakdown
    stats_table = Table(show_header=False, box=None, padding=(0, 2))
    stats_table.add_column("Label", style="bold", min_width=22)
    stats_table.add_column("Value", justify="right")
    stats_table.add_row("Total findings", str(ps.findings_count))
    stats_table.add_row("Data breaches", f"[red]{ps.breaches_count}[/red]" if ps.breaches_count else "0")
    stats_table.add_row("Broker listings", f"[red]{ps.broker_listings}[/red]" if ps.broker_listings else "0")
    stats_table.add_row("Accounts found", str(ps.accounts_found))
    stats_table.add_row("Removals confirmed", f"[green]{ps.removals_confirmed}[/green]" if ps.removals_confirmed else "0")
    stats_table.add_row("Removals pending", f"[yellow]{ps.removals_pending}[/yellow]" if ps.removals_pending else "0")

    console.print()
    console.print(Panel(stats_table, title="Breakdown", border_style="blue"))

    # Risk factors
    if ps.risk_factors:
        risk_lines = "\n".join(f"  [red]-[/red] {rf}" for rf in ps.risk_factors)
        console.print()
        console.print(Panel(risk_lines, title="Risk Factors", border_style="red"))

    # Recommendations
    if ps.recommendations:
        rec_lines = "\n".join(f"  [cyan]{i+1}.[/cyan] {rec}" for i, rec in enumerate(ps.recommendations))
        console.print()
        console.print(Panel(rec_lines, title="Recommendations", border_style="cyan"))

    console.print()


# ============================================================================
# REPORT COMMAND
# ============================================================================

@cli.command("report")
@click.option("--format", "-f", "fmt", type=click.Choice(["table", "json", "csv", "html"]), default="table")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--type", "-t", "report_type", type=click.Choice(["findings", "removals"]), default="findings",
              help="Report type: findings or removals")
@click.pass_context
def report(ctx, fmt, output, report_type):
    """Generate exposure report from scan results."""
    db = ctx.obj["db"]
    profile_name = ctx.obj["profile_name"]

    if fmt == "table":
        from src.reporting.terminal import show_scan_results, show_removal_status
        if report_type == "findings":
            show_scan_results(db, profile_name, console)
        else:
            show_removal_status(db, profile_name, console)
    elif fmt == "json":
        from src.reporting.json_export import export_findings, export_removals
        if report_type == "findings":
            path = export_findings(db, profile_name, output)
        else:
            path = export_removals(db, profile_name, output)
        console.print(f"[green]Exported to: {path}[/green]")
    elif fmt == "csv":
        from src.reporting.csv_export import export_findings, export_removals
        if report_type == "findings":
            path = export_findings(db, profile_name, output)
        else:
            path = export_removals(db, profile_name, output)
        console.print(f"[green]Exported to: {path}[/green]")
    elif fmt == "html":
        from src.reporting.html_export import export_findings, export_removals
        if report_type == "findings":
            path = export_findings(db, profile_name, output)
        else:
            path = export_removals(db, profile_name, output)
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

    US_STATES = {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
    }
    state = click.prompt("State of residence (2-letter code, e.g. IL, CA, TX)", default="US")
    state = state.upper().strip()
    if state not in US_STATES and state != "US":
        console.print(f"[yellow]'{state}' not recognized. Using 'US' as default.[/yellow]")
        state = "US"

    p = Profile(
        name=name,
        first_name=first,
        last_name=last,
        full_name=full,
        email_addresses=emails,
        phone_numbers=phones,
        usernames=usernames,
        jurisdiction=state,
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
        console.print("  Follow-up check: daily at 9 AM")
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

@cli.group(invoke_without_command=True)
@click.option("--priority", "-P", type=click.Choice(["critical", "high", "medium", "low"]), default=None)
@click.pass_context
def brokers(ctx, priority):
    """Manage and inspect data broker definitions."""
    ctx.ensure_object(dict)
    ctx.obj["broker_priority"] = priority
    if ctx.invoked_subcommand is None:
        ctx.invoke(brokers_list)


@brokers.command("list")
@click.pass_context
def brokers_list(ctx):
    """List all configured data brokers."""
    priority = ctx.obj.get("broker_priority")
    all_brokers = load_all_brokers()
    if priority:
        all_brokers = [b for b in all_brokers if b.priority.value == priority]

    if not all_brokers:
        console.print("[yellow]No brokers found.[/yellow]")
        return

    table = Table(title=f"Data Brokers ({len(all_brokers)})")
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

    for b in sorted(all_brokers, key=lambda x: ["critical", "high", "medium", "low"].index(x.priority.value)):
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


@brokers.command("validate")
def brokers_validate():
    """Validate all broker YAML files against the expected schema."""
    import yaml as _yaml

    table = Table(title="Broker Validation Results")
    table.add_column("Slug", style="bold", width=25)
    table.add_column("Status", width=8)
    table.add_column("Errors", width=60)

    ok_count = 0
    warn_count = 0
    fail_count = 0

    for path in sorted(BROKERS_DIR.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        try:
            with open(path) as f:
                data = _yaml.safe_load(f) or {}
        except Exception as e:
            fail_count += 1
            table.add_row(path.stem, "[red]FAIL[/red]", f"YAML parse error: {e}")
            continue

        errors = validate_broker(data, path.name)
        slug = data.get("slug", path.stem)

        if errors:
            warn_count += 1
            table.add_row(
                slug,
                "[yellow]WARN[/yellow]",
                "; ".join(errors),
            )
        else:
            ok_count += 1
            table.add_row(slug, "[green]OK[/green]", "")

    console.print(table)
    console.print(
        f"\n[bold]Summary:[/bold] {ok_count} OK, {warn_count} warnings, "
        f"{fail_count} failures out of {ok_count + warn_count + fail_count} brokers"
    )


# ============================================================================
# DOCTOR COMMAND
# ============================================================================

@cli.command("doctor")
@click.pass_context
def doctor(ctx):
    """Check all dependencies and report their status."""
    from src.config import BIN_DIR

    config = ctx.obj["config"]

    table = Table(title="Privacy Toolkit - Dependency Check")
    table.add_column("Component", style="bold", width=16)
    table.add_column("Status", width=10)
    table.add_column("Details")

    def _ok(details: str):
        return "[green]OK[/green]", details

    def _warn(details: str):
        return "[yellow]WARN[/yellow]", details

    def _missing(details: str):
        return "[red]MISSING[/red]", details

    # 1. Python version
    try:
        ver = sys.version_info
        ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
        if ver >= (3, 12):
            status, detail = _ok(ver_str)
        else:
            status, detail = _warn(f"{ver_str} (3.12+ recommended)")
    except Exception:
        status, detail = _missing("Could not determine Python version")
    table.add_row("Python", status, detail)

    # 2. Playwright + Chromium
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        import playwright as _pw
        pw_version = getattr(_pw, "__version__", "unknown")
        browsers_path = Path.home() / ".cache" / "ms-playwright"
        chromium_dirs = list(browsers_path.glob("chromium-*")) if browsers_path.exists() else []
        if chromium_dirs:
            status, detail = _ok(f"Chromium installed (playwright {pw_version})")
        else:
            status, detail = _warn(
                f"playwright {pw_version}, but Chromium not found. "
                "Run: playwright install chromium"
            )
    except ImportError:
        status, detail = _missing(
            "Not installed. Run: pip install playwright && playwright install chromium"
        )
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("Playwright", status, detail)

    # 3. Holehe
    try:
        import holehe as _holehe
        holehe_version = getattr(_holehe, "__version__", "unknown")
        status, detail = _ok(holehe_version)
    except ImportError:
        status, detail = _missing("Not installed. Run: pip install holehe")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("Holehe", status, detail)

    # 4. Sherlock
    try:
        result = subprocess.run(
            [sys.executable, "-m", "sherlock_project", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            version_out = (result.stdout.strip() or result.stderr.strip())
            status, detail = _ok(version_out if version_out else "installed")
        else:
            status, detail = _missing("Not installed. Run: pip install sherlock-project")
    except subprocess.TimeoutExpired:
        status, detail = _warn("Installed but timed out checking version")
    except FileNotFoundError:
        status, detail = _missing("Not installed. Run: pip install sherlock-project")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("Sherlock", status, detail)

    # 5. Maigret
    try:
        result = subprocess.run(
            [sys.executable, "-m", "maigret", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            version_out = (result.stdout.strip() or result.stderr.strip())
            status, detail = _ok(version_out if version_out else "installed")
        else:
            status, detail = _missing("Not installed. Run: pip install maigret")
    except subprocess.TimeoutExpired:
        status, detail = _warn("Installed but timed out checking version")
    except FileNotFoundError:
        status, detail = _missing("Not installed. Run: pip install maigret")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("Maigret", status, detail)

    # 6. PhoneInfoga
    try:
        phoneinfoga_bin = BIN_DIR / "phoneinfoga"
        if phoneinfoga_bin.exists() and os.access(phoneinfoga_bin, os.X_OK):
            try:
                result = subprocess.run(
                    [str(phoneinfoga_bin), "version"],
                    capture_output=True, text=True, timeout=5,
                )
                version_out = (result.stdout.strip() or result.stderr.strip())
                if version_out:
                    status, detail = _ok(f"{phoneinfoga_bin} ({version_out})")
                else:
                    status, detail = _ok(str(phoneinfoga_bin))
            except Exception:
                status, detail = _ok(str(phoneinfoga_bin))
        elif phoneinfoga_bin.exists():
            status, detail = _warn(f"{phoneinfoga_bin} (not executable)")
        else:
            status, detail = _missing(f"Binary not found at {phoneinfoga_bin}")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("PhoneInfoga", status, detail)

    # 7. SpiderFoot Docker image
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", "ghcr.io/smicallef/spiderfoot:latest"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            status, detail = _ok("Docker image available")
        else:
            status, detail = _missing(
                "Docker image not found. Run: docker pull ghcr.io/smicallef/spiderfoot:latest"
            )
    except FileNotFoundError:
        status, detail = _missing("Docker not installed")
    except subprocess.TimeoutExpired:
        status, detail = _warn("Docker timed out checking image")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("SpiderFoot", status, detail)

    # 8. SMTP configuration
    try:
        smtp = config.smtp
        if smtp.username and smtp.password and smtp.host:
            status, detail = _ok(f"{smtp.host}:{smtp.port}")
        elif smtp.host:
            missing_parts = []
            if not smtp.username:
                missing_parts.append("username")
            if not smtp.password:
                missing_parts.append("password")
            status, detail = _warn(
                f"{smtp.host}:{smtp.port} (missing {', '.join(missing_parts)})"
            )
        else:
            status, detail = _warn("No SMTP host configured")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("SMTP", status, detail)

    # 9. HIBP API key
    try:
        hibp_key = config.hibp_api_key
        if hibp_key:
            masked = hibp_key[:4] + "..." + hibp_key[-4:] if len(hibp_key) > 8 else "***"
            status, detail = _ok(f"Key configured ({masked})")
        else:
            status, detail = _warn("No API key configured (free tier only, limited)")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("HIBP API", status, detail)

    # 10. Signal API
    try:
        sig = config.signal
        if sig.enabled and sig.api_url:
            try:
                import requests as _requests
                resp = _requests.get(f"{sig.api_url}/v1/about", timeout=5)
                if resp.status_code == 200:
                    status, detail = _ok(f"{sig.api_url} (reachable)")
                else:
                    status, detail = _warn(f"{sig.api_url} (HTTP {resp.status_code})")
            except Exception:
                status, detail = _warn(f"{sig.api_url} (configured but not reachable)")
        elif sig.enabled:
            status, detail = _warn("Enabled but no API URL configured")
        else:
            status, detail = _warn("Notifications disabled")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("Signal", status, detail)

    # 11. Database
    try:
        db_path = Path(config.db_path)
        if not db_path.is_absolute():
            db_path = TOOLKIT_DIR / db_path
        if db_path.exists():
            size_bytes = db_path.stat().st_size
            if size_bytes < 1024:
                size_str = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.0f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                conn.execute("SELECT 1")
                conn.close()
                status, detail = _ok(f"{config.db_path} ({size_str})")
            except Exception:
                status, detail = _warn(
                    f"{config.db_path} ({size_str}, not readable as SQLite)"
                )
        else:
            status, detail = _warn(
                f"Not found at {config.db_path} (will be created on first scan)"
            )
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("Database", status, detail)

    # 12. Broker YAML files
    try:
        if BROKERS_DIR.exists():
            broker_files = [
                f for f in BROKERS_DIR.glob("*.yaml") if not f.stem.startswith("_")
            ]
            count = len(broker_files)
            if count > 0:
                status, detail = _ok(f"{count} loaded")
            else:
                status, detail = _warn("No broker YAML files found")
        else:
            status, detail = _missing(f"Brokers directory not found: {BROKERS_DIR}")
    except Exception as e:
        status, detail = _missing(f"Error: {e}")
    table.add_row("Brokers", status, detail)

    console.print()
    console.print(table)
    console.print()


def main():
    cli(obj={})


if __name__ == "__main__":
    main()
