from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="EbayWorkflows local CLI.")
console = Console()


@app.callback()
def _bootstrap(
    log_level: str | None = typer.Option(
        None,
        envvar="LOG_LEVEL",
        help="Log level (debug, info, warning, error).",
    ),
) -> None:
    from ebay_workflows.logging_config import configure_logging

    configure_logging(log_level or "info")

_ENV_OVERRIDE_KEYS = (
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "EBAY_SANDBOX_CLIENT_ID",
    "EBAY_SANDBOX_CLIENT_SECRET",
    "EBAY_USE_SANDBOX",
    "DISABLE_LIVE_API_WRITES",
    "CARDMARKET_BULK_FILE_PATH",
)


def _dotenv_value(key: str) -> str | None:
    env_path = Path(".env")
    if not env_path.is_file():
        return None
    prefix = f"{key}="
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        return stripped[len(prefix) :].strip()
    return None


def _warn_shell_env_overrides() -> None:
    for key in _ENV_OVERRIDE_KEYS:
        if key not in os.environ:
            continue
        file_value = _dotenv_value(key)
        if file_value is None or os.environ[key] == file_value:
            continue
        console.print(
            f"[yellow]Warning:[/yellow] shell variable [cyan]{key}[/cyan] overrides `.env`. "
            "Run [cyan]./scripts/clear-ebay-env-overrides.ps1[/cyan] or open a new terminal."
        )
