"""~/.commune/config.toml read/write helpers.

Config file location follows XDG on Linux, ~/Library/Application Support on macOS,
%APPDATA% on Windows — via platformdirs. Falls back gracefully if missing.

File is chmod 600 on creation to protect the api_key.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any, Optional

from platformdirs import user_config_dir

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redef]


# ── paths ─────────────────────────────────────────────────────────────────────

def config_dir() -> Path:
    """Return the Commune config directory (creates if missing)."""
    # Honour an explicit override for testing
    override = os.environ.get("COMMUNE_CONFIG_DIR")
    if override:
        path = Path(override)
    else:
        path = Path(user_config_dir("commune", appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / "config.toml"


# ── read ──────────────────────────────────────────────────────────────────────

def load_config() -> dict[str, Any]:
    """Load config.toml. Returns empty dict if file does not exist."""
    p = config_path()
    if not p.exists():
        return {}
    try:
        with open(p, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def get_value(key: str) -> Optional[str]:
    """Get a single config value. Returns None if not set."""
    cfg = load_config()
    return cfg.get(key)


# ── write ─────────────────────────────────────────────────────────────────────

def _write_toml(data: dict[str, Any]) -> None:
    """Write dict to config.toml as TOML. Simple hand-built serializer
    (avoids tomli-w dependency while keeping the file human-readable)."""
    p = config_path()
    lines = []
    for k, v in sorted(data.items()):
        if isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{k} = "{escaped}"')
        elif isinstance(v, bool):
            lines.append(f"{k} = {'true' if v else 'false'}")
        elif isinstance(v, int):
            lines.append(f"{k} = {v}")
        else:
            lines.append(f'{k} = "{v}"')
    content = "\n".join(lines) + "\n"
    p.write_text(content, encoding="utf-8")
    # Restrict permissions to owner-only (ignored on Windows)
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def set_value(key: str, value: str) -> None:
    """Set a config key and persist to disk."""
    cfg = load_config()
    cfg[key] = value
    _write_toml(cfg)


def delete_value(key: str) -> bool:
    """Remove a key from config. Returns True if it existed."""
    cfg = load_config()
    if key in cfg:
        del cfg[key]
        _write_toml(cfg)
        return True
    return False


# ── known keys ────────────────────────────────────────────────────────────────

KNOWN_KEYS = {
    "api_key": "Commune API key (comm_...)",
    "wallet_key": "x402 wallet private key (0x...) — pay-per-call with USDC",
    "base_url": "API base URL (default: https://api.commune.email)",
}


def mask(value: Optional[str], visible: int = 8) -> str:
    """Mask a secret value, showing only the first N characters."""
    if not value:
        return "(not set)"
    if len(value) <= visible:
        return value
    return value[:visible] + "..."
