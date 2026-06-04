from __future__ import annotations

import shutil
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_cli_launch(argv: list[str]) -> tuple[str, list[str]]:
    """Return (program, args) to spawn the ebay-workflows CLI."""
    executable = shutil.which("ebay-workflows")
    if executable:
        return executable, argv[1:]
    return sys.executable, ["-m", "ebay_workflows", *argv[1:]]
