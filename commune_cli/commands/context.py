"""commune context — full org state snapshot in one call.

The equivalent of opening a dashboard and seeing every widget at once.
Fetches auth, domains, inboxes, delivery health, and credits in parallel
and presents them as a single unified view.
"""

from __future__ import annotations

import time
from typing import Any, Optional

import typer

from ..output import print_json

app = typer.Typer(help="Full org state snapshot — auth, domains, inboxes, delivery, credits.", no_args_is_help=False)


def _fetch_context(client: Any) -> dict:
    """Fetch all org context from multiple endpoints. Never raises."""
    ctx: dict = {
        "auth": {},
        "domains": [],
        "inboxes": [],
        "delivery": {},
        "webhooks": {},
        "credits": {},
        "phone_numbers": [],
    }

    # Auth / org info
    try:
        r = client.get("/v1/agent/org")
        if r.is_success:
            org = r.json()
            ctx["auth"] = {
                "org_name": org.get("name", ""),
                "org_id": org.get("id", ""),
                "tier": org.get("tier", ""),
                "status": org.get("status", ""),
            }
    except Exception:
        ctx["auth"] = {"error": "could not reach API"}

    # Domains
    try:
        r = client.get("/v1/domains")
        if r.is_success:
            data = r.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                ctx["domains"] = [
                    {
                        "id": d.get("id", ""),
                        "name": d.get("name", ""),
                        "status": d.get("status", ""),
                    }
                    for d in items
                ]
    except Exception:
        pass

    # Inboxes
    try:
        r = client.get("/v1/inboxes")
        if r.is_success:
            data = r.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                ctx["inboxes"] = [
                    {
                        "id": d.get("id", ""),
                        "address": d.get("address", ""),
                        "display_name": d.get("displayName") or d.get("display_name"),
                        "webhook": bool(d.get("webhook")),
                        "domain_name": d.get("domain_name", ""),
                    }
                    for d in items
                ]
    except Exception:
        pass

    # Delivery metrics (7d)
    try:
        # Need a domain_id for metrics
        domain_id = ctx["domains"][0]["id"] if ctx["domains"] else None
        if domain_id:
            r = client.get("/v1/delivery/metrics", params={"domain_id": domain_id, "period": "7d"})
            if r.is_success:
                ctx["delivery"] = r.json()
    except Exception:
        pass

    # Webhook health
    try:
        r = client.get("/v1/webhooks/health")
        if r.is_success:
            ctx["webhooks"] = r.json()
    except Exception:
        pass

    # Credits
    try:
        r = client.get("/v1/credits/balance")
        if r.is_success:
            ctx["credits"] = r.json()
    except Exception:
        pass

    # Phone numbers
    try:
        r = client.get("/v1/phone-numbers")
        if r.is_success:
            data = r.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                ctx["phone_numbers"] = [
                    {
                        "id": d.get("id", ""),
                        "number": d.get("phoneNumber") or d.get("phone_number", ""),
                        "friendly_name": d.get("friendlyName") or d.get("friendly_name"),
                        "type": d.get("type", ""),
                    }
                    for d in items
                ]
    except Exception:
        pass

    return ctx


# ── Animated TTY display ──────────────────────────────────────────────────────


def _show_context_tty(ctx_data: dict) -> None:
    """Animated section-by-section reveal of org context."""
    from rich.console import Console, Group
    from rich.live import Live
    from rich.padding import Padding
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    console = Console(highlight=False)

    # ── Build sections ────────────────────────────────────────────────

    def _header() -> Text:
        t = Text(no_wrap=True)
        t.append("  COMMUNE", style="bold rgb(0,210,255)")
        t.append("  ·  ", style="dim")
        t.append("Organization Context", style="italic white")
        return t

    def _auth_section() -> Panel:
        auth = ctx_data.get("auth", {})
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column("key", style="bold dim", no_wrap=True)
        tbl.add_column("value")
        tbl.add_row("org", auth.get("org_name", "[dim]—[/dim]"))
        tbl.add_row("id", auth.get("org_id", "[dim]—[/dim]"))
        tbl.add_row("tier", f"[bold]{auth.get('tier', '—')}[/bold]")
        tbl.add_row("status", auth.get("status", "[dim]—[/dim]"))
        return Panel(tbl, title="[bold bright_cyan]Auth[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))

    def _domains_section() -> Panel:
        domains = ctx_data.get("domains", [])
        if not domains:
            return Panel("[dim]No domains configured[/dim]", title="[bold bright_cyan]Domains[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column("name", style="bold white")
        tbl.add_column("status")
        tbl.add_column("id", style="dim")
        for d in domains:
            status = d.get("status", "")
            style = "green" if status == "verified" else "yellow"
            tbl.add_row(d.get("name", ""), f"[{style}]{status}[/{style}]", d.get("id", "")[:12] + "…")
        return Panel(tbl, title="[bold bright_cyan]Domains[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))

    def _inboxes_section() -> Panel:
        inboxes = ctx_data.get("inboxes", [])
        if not inboxes:
            return Panel("[dim]No inboxes[/dim]", title="[bold bright_cyan]Inboxes[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column("address", style="bold white")
        tbl.add_column("webhook")
        tbl.add_column("id", style="dim")
        for inbox in inboxes:
            wh = "[green]✓[/green]" if inbox.get("webhook") else "[dim]—[/dim]"
            tbl.add_row(inbox.get("address", ""), wh, inbox.get("id", "")[:12] + "…")
        return Panel(tbl, title=f"[bold bright_cyan]Inboxes ({len(inboxes)})[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))

    def _delivery_section() -> Panel:
        delivery = ctx_data.get("delivery", {})
        if not delivery:
            return Panel("[dim]No delivery data[/dim]", title="[bold bright_cyan]Delivery (7d)[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column("metric", style="bold dim")
        tbl.add_column("value")
        for key in ["sent", "delivered", "bounced", "complained", "failed"]:
            val = delivery.get(key, "—")
            style = "red" if key in ("bounced", "complained", "failed") and val and val != "—" and int(str(val)) > 0 else "white"
            tbl.add_row(key, f"[{style}]{val}[/{style}]")
        return Panel(tbl, title="[bold bright_cyan]Delivery (7d)[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))

    def _phone_section() -> Optional[Panel]:
        phones = ctx_data.get("phone_numbers", [])
        if not phones:
            return None
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column("number", style="bold white")
        tbl.add_column("name", style="dim")
        tbl.add_column("type", style="dim")
        for p in phones:
            tbl.add_row(p.get("number", ""), p.get("friendly_name") or "—", p.get("type", ""))
        return Panel(tbl, title=f"[bold bright_cyan]Phone Numbers ({len(phones)})[/bold bright_cyan]", border_style="rgb(0,178,255)", padding=(0, 1))

    # ── Sections to reveal ────────────────────────────────────────────

    sections = [
        _auth_section,
        _domains_section,
        _inboxes_section,
        _delivery_section,
    ]
    phone = _phone_section()
    if phone:
        sections.append(lambda: phone)  # type: ignore[arg-type]

    def build_frame(n: int) -> Group:
        parts: list = []
        parts.append(Padding(Rule(characters="─", style="rgb(0,178,255)"), (0, 2, 0, 2)))
        parts.append(Padding(_header(), (0, 2, 0, 2)))
        parts.append(Text())
        for i in range(min(n, len(sections))):
            parts.append(Padding(sections[i](), (0, 2, 0, 2)))
        if n > len(sections):
            parts.append(Padding(Rule(characters="─", style="dim"), (0, 2, 0, 2)))
        return Group(*parts)

    if not console.is_terminal:
        console.print(build_frame(len(sections) + 1))
        return

    with Live(build_frame(0), console=console, refresh_per_second=30, transient=False) as live:
        for i in range(1, len(sections) + 2):
            time.sleep(0.1)
            live.update(build_frame(i))


# ── Command ───────────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def context(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Full org state snapshot — auth, domains, inboxes, delivery, credits.

    Fetches everything in one call so an agent can orient itself immediately.

    For JSON:  commune context --json
    """
    from ..client import CommuneClient
    from ..errors import auth_required_error
    from ..state import AppState

    state: AppState = ctx.obj or AppState()
    if not state.has_any_auth():
        auth_required_error(json_output=json_output or state.should_json())

    client = CommuneClient.from_state(state)
    ctx_data = _fetch_context(client)

    if json_output or state.should_json():
        print_json(ctx_data)
        return

    _show_context_tty(ctx_data)
