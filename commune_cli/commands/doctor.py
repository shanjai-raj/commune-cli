"""commune doctor — health diagnostics with animated progress.

Runs sequential checks: auth, connectivity, domains (DNS), webhooks,
deliverability. Each check shows a spinner then resolves to pass/warn/fail.
"""

from __future__ import annotations

import time
from typing import Any

import typer

from ..output import print_json

app = typer.Typer(help="Run health diagnostics: auth, connectivity, DNS, webhooks, deliverability.", no_args_is_help=False)


# ── Check runners ─────────────────────────────────────────────────────────────


def _check_auth(client: Any, api_key: str) -> dict:
    """Check API authentication."""
    result: dict = {"name": "auth", "status": "pass", "details": {}}
    if not api_key:
        result["status"] = "fail"
        result["details"] = {"message": "No API key configured"}
        return result

    # Mask key
    result["details"]["key_prefix"] = api_key[:12] + "…" if len(api_key) > 12 else api_key

    try:
        r = client.get("/v1/agent/org")
        if r.is_success:
            org = r.json()
            result["details"]["org_name"] = org.get("name", "")
            result["details"]["tier"] = org.get("tier", "")
        else:
            result["status"] = "fail"
            result["details"]["message"] = f"HTTP {r.status_code}"
    except Exception as e:
        result["status"] = "fail"
        result["details"]["message"] = str(e)

    return result


def _check_connectivity(client: Any) -> dict:
    """Check API connectivity and latency."""
    result: dict = {"name": "connectivity", "status": "pass", "details": {}}
    try:
        start = time.monotonic()
        r = client.get("/v1/domains")
        elapsed = round((time.monotonic() - start) * 1000)
        result["details"]["latency_ms"] = elapsed
        result["details"]["base_url"] = client.base_url
        if not r.is_success and r.status_code not in (401, 403):
            result["status"] = "warn"
            result["details"]["http_status"] = r.status_code
    except Exception as e:
        result["status"] = "fail"
        result["details"]["message"] = str(e)

    return result


def _check_domains(client: Any) -> dict:
    """Check domain DNS verification status."""
    result: dict = {"name": "domains", "status": "pass", "details": {"domains": []}}
    try:
        r = client.get("/v1/domains")
        if not r.is_success:
            result["status"] = "warn"
            result["details"]["message"] = f"Could not fetch domains (HTTP {r.status_code})"
            return result

        data = r.json()
        items = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(items, list) or not items:
            result["details"]["message"] = "No custom domains configured"
            return result

        for d in items:
            domain_info: dict = {
                "name": d.get("name", ""),
                "status": d.get("status", "unknown"),
            }

            # Try to get DNS records for each domain
            did = d.get("id", "")
            if did:
                try:
                    r2 = client.get(f"/v1/domains/{did}/records")
                    if r2.is_success:
                        records = r2.json()
                        rec_items = records.get("data", records) if isinstance(records, dict) else records
                        if isinstance(rec_items, list):
                            verified = sum(1 for rec in rec_items if rec.get("status") == "verified" or rec.get("verified"))
                            total = len(rec_items)
                            domain_info["dns_records"] = f"{verified}/{total} verified"
                            if verified < total:
                                result["status"] = "warn"
                except Exception:
                    pass

            if d.get("status") not in ("verified", "active"):
                result["status"] = "warn"

            result["details"]["domains"].append(domain_info)

    except Exception as e:
        result["status"] = "fail"
        result["details"]["message"] = str(e)

    return result


def _check_webhooks(client: Any) -> dict:
    """Check webhook health."""
    result: dict = {"name": "webhooks", "status": "pass", "details": {}}
    try:
        r = client.get("/v1/webhooks/health")
        if r.is_success:
            health = r.json()
            result["details"] = health
            # Check success rate
            rate = health.get("success_rate") or health.get("successRate")
            if rate is not None:
                try:
                    rate_float = float(rate)
                    if rate_float < 0.9:
                        result["status"] = "fail"
                    elif rate_float < 0.99:
                        result["status"] = "warn"
                except (ValueError, TypeError):
                    pass
        else:
            result["details"]["message"] = f"HTTP {r.status_code}"
            if r.status_code == 404:
                result["details"]["message"] = "No webhook deliveries yet"
            else:
                result["status"] = "warn"
    except Exception as e:
        result["status"] = "fail"
        result["details"]["message"] = str(e)

    return result


def _check_deliverability(client: Any, domain_id: str | None) -> dict:
    """Check deliverability metrics."""
    result: dict = {"name": "deliverability", "status": "pass", "details": {}}

    if not domain_id:
        result["details"]["message"] = "No domain to check"
        return result

    try:
        r = client.get("/v1/delivery/metrics", params={"domain_id": domain_id, "period": "7d"})
        if r.is_success:
            metrics = r.json()
            result["details"] = metrics
            # Flag high bounce or complaint rates
            bounce_rate = metrics.get("bounce_rate") or metrics.get("bounceRate", 0)
            complaint_rate = metrics.get("complaint_rate") or metrics.get("complaintRate", 0)
            try:
                if float(bounce_rate) > 0.05:
                    result["status"] = "fail"
                elif float(bounce_rate) > 0.02:
                    result["status"] = "warn"
                if float(complaint_rate) > 0.001:
                    result["status"] = "fail"
            except (ValueError, TypeError):
                pass
        else:
            result["details"]["message"] = f"HTTP {r.status_code}"
            if r.status_code != 404:
                result["status"] = "warn"
    except Exception as e:
        result["status"] = "fail"
        result["details"]["message"] = str(e)

    return result


# ── Animated TTY display ──────────────────────────────────────────────────────


_STATUS_ICONS = {
    "pass": "[green]✓[/green]",
    "warn": "[yellow]⚠[/yellow]",
    "fail": "[red]✗[/red]",
    "running": "[bright_cyan]◌[/bright_cyan]",
    "pending": "[dim]○[/dim]",
}

_CHECK_LABELS = {
    "auth": "Authentication",
    "connectivity": "API Connectivity",
    "domains": "Domain DNS",
    "webhooks": "Webhook Health",
    "deliverability": "Deliverability",
}


def _show_doctor_tty(results: list[dict]) -> None:
    """Animated check-by-check reveal."""
    from rich.console import Console, Group
    from rich.live import Live
    from rich.padding import Padding
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    console = Console(highlight=False)

    check_names = [r["name"] for r in results]

    def build_frame(completed: int, running: bool = False) -> Group:
        parts: list = []

        # Header
        header = Text(no_wrap=True)
        header.append("  COMMUNE", style="bold rgb(0,210,255)")
        header.append("  ·  ", style="dim")
        header.append("Health Diagnostics", style="italic white")
        parts.append(Padding(Rule(characters="─", style="rgb(0,178,255)"), (0, 2, 0, 2)))
        parts.append(Padding(header, (0, 2, 0, 2)))
        parts.append(Text())

        # Checks
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column("icon", no_wrap=True, width=3)
        tbl.add_column("name", style="white", no_wrap=True, min_width=20)
        tbl.add_column("detail", style="dim")

        for i, name in enumerate(check_names):
            label = _CHECK_LABELS.get(name, name)
            if i < completed:
                # Completed check
                r = results[i]
                icon = _STATUS_ICONS[r["status"]]
                detail = _format_check_detail(r)
                tbl.add_row(icon, label, detail)
            elif i == completed and running:
                # Currently running
                tbl.add_row(_STATUS_ICONS["running"], f"[bright_cyan]{label}[/bright_cyan]", "")
            else:
                # Pending
                tbl.add_row(_STATUS_ICONS["pending"], f"[dim]{label}[/dim]", "")

        parts.append(Padding(tbl, (0, 2, 0, 4)))

        # Summary (after all complete)
        if completed == len(check_names) and not running:
            parts.append(Text())
            passes = sum(1 for r in results if r["status"] == "pass")
            warns = sum(1 for r in results if r["status"] == "warn")
            fails = sum(1 for r in results if r["status"] == "fail")
            summary = Text()
            summary.append(f"  {passes} passed", style="green" if passes else "dim")
            if warns:
                summary.append(f"  {warns} warnings", style="yellow")
            if fails:
                summary.append(f"  {fails} failed", style="red")
            parts.append(Padding(summary, (0, 2, 0, 2)))
            parts.append(Padding(Rule(characters="─", style="dim"), (0, 2, 0, 2)))

        return Group(*parts)

    if not console.is_terminal:
        console.print(build_frame(len(check_names), running=False))
        return

    with Live(build_frame(0, running=False), console=console, refresh_per_second=30, transient=False) as live:
        for i in range(len(check_names)):
            # Show running state
            live.update(build_frame(i, running=True))
            time.sleep(0.15)
            # Show completed
            live.update(build_frame(i + 1, running=False))
            time.sleep(0.06)
        # Final summary
        time.sleep(0.1)
        live.update(build_frame(len(check_names), running=False))


def _format_check_detail(check: dict) -> str:
    """Format a single check's detail as a short string for the table."""
    d = check.get("details", {})
    name = check["name"]

    if name == "auth":
        prefix = d.get("key_prefix", "")
        tier = d.get("tier", "")
        org = d.get("org_name", "")
        parts = [p for p in [prefix, org, tier] if p]
        return " · ".join(parts) if parts else d.get("message", "")

    if name == "connectivity":
        latency = d.get("latency_ms")
        if latency is not None:
            return f"{latency}ms"
        return d.get("message", "")

    if name == "domains":
        domains = d.get("domains", [])
        if not domains:
            return d.get("message", "none")
        parts = []
        for dom in domains:
            parts.append(f"{dom['name']} ({dom.get('status', '?')})")
        return " · ".join(parts)

    if name == "webhooks":
        rate = d.get("success_rate") or d.get("successRate")
        if rate is not None:
            try:
                return f"{float(rate)*100:.1f}% success"
            except (ValueError, TypeError):
                pass
        return d.get("message", "")

    if name == "deliverability":
        sent = d.get("sent")
        if sent is not None:
            bounce = d.get("bounce_rate") or d.get("bounceRate", 0)
            complaint = d.get("complaint_rate") or d.get("complaintRate", 0)
            try:
                return f"{sent} sent · {float(bounce)*100:.1f}% bounce · {float(complaint)*100:.2f}% complaint"
            except (ValueError, TypeError):
                return f"{sent} sent"
        return d.get("message", "")

    return str(d) if d else ""


# ── Command ───────────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def doctor(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Run health diagnostics: auth, connectivity, DNS, webhooks, deliverability.

    Checks everything and reports pass/warn/fail for each subsystem.

    For JSON:  commune doctor --json
    """
    from ..client import CommuneClient
    from ..errors import auth_required_error
    from ..state import AppState

    state: AppState = ctx.obj or AppState()
    if not state.has_any_auth():
        auth_required_error(json_output=json_output or state.should_json())

    client = CommuneClient.from_state(state)

    # Run checks sequentially (they're fast, and order matters for the animation)
    results: list[dict] = []

    results.append(_check_auth(client, state.api_key or ""))
    results.append(_check_connectivity(client))

    domain_result = _check_domains(client)
    results.append(domain_result)

    results.append(_check_webhooks(client))

    # Get first domain ID for deliverability check
    domain_id = None
    domains = domain_result.get("details", {}).get("domains", [])
    # Also try fetching from domain list result
    try:
        r = client.get("/v1/domains")
        if r.is_success:
            data = r.json()
            items = data.get("data", data) if isinstance(data, dict) else data
            if isinstance(items, list) and items:
                domain_id = items[0].get("id")
    except Exception:
        pass

    results.append(_check_deliverability(client, domain_id))

    if json_output or state.should_json():
        # Compute overall status
        statuses = [r["status"] for r in results]
        if "fail" in statuses:
            overall = "fail"
        elif "warn" in statuses:
            overall = "warn"
        else:
            overall = "pass"
        print_json({"status": overall, "checks": results})
        return

    _show_doctor_tty(results)
