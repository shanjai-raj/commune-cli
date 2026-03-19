"""AppState — global state threaded through typer ctx.obj."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class AppState:
    """Holds global CLI flags and resolved configuration.

    Passed as ctx.obj from the root callback down to every subcommand.
    Commands read from this object — never from environment variables directly.
    """

    # --- auth (resolved: flag > env > config) ---
    api_key: Optional[str] = None
    wallet_key: Optional[str] = None

    # --- connection ---
    base_url: str = "https://api.commune.email"

    # --- output ---
    json_output: bool = False                  # True when --json or not a TTY
    quiet: bool = False
    no_color: bool = False

    def is_tty(self) -> bool:
        return sys.stdout.isatty()

    def should_json(self) -> bool:
        """Return True if output should be machine-readable JSON."""
        return self.json_output or not self.is_tty()

    def has_any_auth(self) -> bool:
        return bool(self.api_key) or bool(self.wallet_key)
