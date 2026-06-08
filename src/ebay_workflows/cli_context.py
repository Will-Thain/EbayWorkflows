from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import typer
from pydantic import ValidationError
from rich.console import Console
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .config import Settings
from .db import build_engine, build_session_factory

_console = Console()


def cli_console() -> Console:
    return _console


def load_settings(*, action: str) -> Settings:
    """Load Settings or exit with code 2 using a command-specific message."""
    try:
        return Settings()
    except ValidationError as exc:
        _console.print(f"[bold red]Cannot {action}:[/bold red]")
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", []))
            _console.print(f"- {location}: {error.get('msg')}")
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        _console.print(f"[bold red]Cannot {action}:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc


@contextmanager
def cli_session(*, action: str, settings: Settings | None = None) -> Iterator[tuple[Settings, Session]]:
    resolved = settings or load_settings(action=action)
    session_factory = build_session_factory(resolved)
    with session_factory() as session:
        yield resolved, session


@contextmanager
def cli_engine(*, action: str, settings: Settings | None = None) -> Iterator[tuple[Settings, Engine]]:
    resolved = settings or load_settings(action=action)
    yield resolved, build_engine(resolved)
