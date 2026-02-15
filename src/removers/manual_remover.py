"""Generate manual opt-out instructions for brokers that need human action."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from src.models import Broker, OptOutMethodType


def show_manual_instructions(brokers: list[Broker], console: Console | None = None) -> None:
    console = console or Console()
    manual_brokers = []

    for broker in brokers:
        for method in broker.methods:
            if method.type in (OptOutMethodType.MANUAL, OptOutMethodType.PHONE):
                manual_brokers.append((broker, method))
                break

    if not manual_brokers:
        console.print("[green]No brokers require manual action.[/green]")
        return

    console.print(f"\n[bold]Manual Opt-Out Required for {len(manual_brokers)} Brokers[/bold]\n")

    for broker, method in manual_brokers:
        title = f"{broker.name} [{broker.priority.value.upper()}]"
        body = ""

        if method.type == OptOutMethodType.PHONE:
            body += f"[bold]Call:[/bold] {method.number}\n"
        if method.instructions:
            body += f"[bold]Instructions:[/bold] {method.instructions}\n"
        if method.url:
            body += f"[bold]URL:[/bold] {method.url}\n"
        if broker.notes:
            body += f"[dim]{broker.notes}[/dim]"

        console.print(Panel(body.strip(), title=title, border_style="yellow"))
