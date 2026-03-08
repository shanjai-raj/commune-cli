"""Entry point for the Commune CLI."""

from __future__ import annotations

from typing import Optional

import typer
from rich import print as rprint

from . import __version__
from .banner import show_banner
from .config import load_config
from .state import AppState

from .commands import (
    config_cmd,
    context,
    describe,
    doctor,
    domains,
    inboxes,
    messages,
    threads,
    attachments,
    search,
    delivery,
    webhooks,
    dmarc,
    data,
    phone_numbers,
    sms,
    credits,
)

app = typer.Typer(
    name="commune",
    help=(
        "Commune email API — official CLI.\n\n"
        "Covers every API surface: domains, inboxes, messages, threads, "
        "attachments, search, delivery, webhooks, DMARC, and data.\n\n"
        "Auth: set COMMUNE_API_KEY or use --api-key."
    ),
    no_args_is_help=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# ── Agent-native commands (top-level) ─────────────────────────────────────
app.add_typer(describe.app,     name="describe",      help="Machine-readable API surface manifest.")
app.add_typer(context.app,      name="context",       help="Full org snapshot: auth, domains, inboxes, delivery, credits.")
app.add_typer(doctor.app,       name="doctor",        help="Health diagnostics: auth, connectivity, DNS, webhooks.")

# ── Resource commands ─────────────────────────────────────────────────────
app.add_typer(config_cmd.app,  name="config",      help="Manage CLI configuration (~/.commune/config.toml).")
app.add_typer(domains.app,     name="domains",      help="Domain management: list, create, verify, DNS records.")
app.add_typer(inboxes.app,     name="inboxes",      help="Inbox management: create, update, delete, webhooks, extraction schema.")
app.add_typer(messages.app,    name="messages",     help="Send and list emails.")
app.add_typer(threads.app,     name="threads",      help="Thread management: list, status, tags, assignment.")
app.add_typer(attachments.app, name="attachments",  help="Upload attachments and get download URLs.")
app.add_typer(search.app,      name="search",       help="Full-text search across threads.")
app.add_typer(delivery.app,    name="delivery",     help="Delivery metrics, events, and suppressions.")
app.add_typer(webhooks.app,    name="webhooks",     help="Webhook delivery log: list, retry, health.")
app.add_typer(dmarc.app,       name="dmarc",        help="DMARC reports and summary.")
app.add_typer(data.app,        name="data",         help="Data deletion requests (GDPR / destructive).")
app.add_typer(phone_numbers.app, name="phone-numbers", help="Phone number management: list, get, settings.")
app.add_typer(sms.app,           name="sms",           help="Send SMS and manage conversations.")
app.add_typer(credits.app,       name="credits",       help="Credit balance and available bundles.")


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar="COMMUNE_API_KEY",
        help="Commune API key (comm_...). Overrides config file.",
        show_default=False,
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        envvar="COMMUNE_BASE_URL",
        help="API base URL. Default: https://api.commune.email",
        show_default=False,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output raw JSON (default when stdout is not a TTY).",
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress status messages."),
    no_color: bool = typer.Option(False, "--no-color", help="Disable color output."),
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit.", is_eager=True),
) -> None:
    if version:
        rprint(f"commune-cli {__version__}")
        raise typer.Exit()

    cfg = load_config()

    resolved_api_key = api_key or cfg.get("api_key")
    resolved_base_url = base_url or cfg.get("base_url") or "https://api.commune.email"

    state = AppState(
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        json_output=json_output,
        quiet=quiet,
        no_color=no_color,
    )
    ctx.obj = state

    if ctx.invoked_subcommand is None:
        show_banner(no_color=no_color)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
