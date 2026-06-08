"""One-off helper: split monolithic cli.py into ebay_workflows/cli/ package."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "ebay_workflows"
CLI_FILE = ROOT / "cli.py"
PKG = ROOT / "cli"
CMD = PKG / "commands"

BOOTSTRAP = '''from __future__ import annotations

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
'''

COMMON = '''from __future__ import annotations

import httpx
import typer
from pydantic import ValidationError
from rich.table import Table
from sqlalchemy.exc import OperationalError

from ebay_workflows.cli.bootstrap import app, console, _warn_shell_env_overrides
from ebay_workflows.cli_context import cli_engine, cli_session, load_settings
from ebay_workflows.config import Settings
from ebay_workflows.exceptions import AuthenticationError

'''

EXTRA: dict[str, str] = {
    "env.py": (
        "from ebay_workflows.models import Base\n"
        "from ebay_workflows.services.db_indexes import ensure_performance_indexes\n"
        "from ebay_workflows.integrations.ebay import verify_ebay_credentials\n"
        "from ebay_workflows.services.health_checks import collect_operational_health\n"
        "from ebay_workflows.services.embedding_index import index_exists\n"
        "from ebay_workflows.services.ingest_helpers import max_listings_per_query\n"
    ),
    "ingest.py": (
        "from ebay_workflows.services.ingest_helpers import resolve_max_pages\n"
        "from ebay_workflows.workflow_phase1 import retry_failed_image_downloads, run_phase1\n"
        "from ebay_workflows.integrations.scryfall import sync_scryfall_bulk\n"
        "from ebay_workflows.workflow_phase2 import upsert_scryfall_cards\n"
        "from ebay_workflows.integrations.cardmarket import load_cardmarket_bulk_rows\n"
        "from ebay_workflows.workflow_phase3 import sync_cardmarket_prices\n"
        "from ebay_workflows.integrations.cardmarket_bulk import download_and_build_singles_csv\n"
    ),
    "index.py": (
        "from ebay_workflows.services.embedding_index import (\n"
        "    append_faiss_batch,\n"
        "    build_faiss_index,\n"
        "    build_faiss_index_all_batches,\n"
        "    count_indexable_art_cards,\n"
        "    indexed_scryfall_ids,\n"
        ")\n"
        "from ebay_workflows.services.set_symbol_match import build_set_symbol_templates, set_symbol_template_dir\n"
    ),
    "phases.py": (
        "from ebay_workflows.services.clear_matching_data import clear_matching_artifacts, count_matching_artifacts\n"
        "from ebay_workflows.services.ingest_helpers import resolve_max_pages\n"
        "from ebay_workflows.pipeline_resume import ResumablePipelineConfig, run_resumable_pipeline\n"
        "from ebay_workflows.workflow_phase2 import load_cards_from_cache, run_phase2_title_match\n"
        "from ebay_workflows.workflow_phase3 import run_phase3_join\n"
        "from ebay_workflows.workflow_phase4 import run_phase4_ranking\n"
        "from ebay_workflows.workflow_phase5 import run_phase5_ocr_verification\n"
        "from ebay_workflows.workflow_phase6 import run_phase6_bulk_lot_detection\n"
    ),
    "monitor.py": (
        "from ebay_workflows.hardening import run_data_integrity_checks\n"
        "from ebay_workflows.services.match_stats import collect_match_stats\n"
        "from ebay_workflows.services.pipeline_progress import collect_pipeline_progress\n"
        "from ebay_workflows.services.stale_workflows import clear_stale_workflow_steps, list_running_workflow_views\n"
        "from ebay_workflows.services.ranked_export import fetch_ranked_listings, write_ranked_json\n"
    ),
}

GROUPS: dict[str, tuple[str, ...]] = {
    "env.py": ("validate-env", "ebay-auth-check", "init-db", "ensure-db-indexes"),
    "ingest.py": (
        "run",
        "retry-failed-images",
        "sync-scryfall",
        "download-cardmarket-bulk",
        "sync-cardmarket",
    ),
    "index.py": ("build-set-symbol-templates", "build-faiss-index", "build-faiss-index-batches"),
    "phases.py": (
        "phase2-match-title",
        "phase3-join-prices",
        "phase4-rank",
        "phase5-verify-ocr",
        "phase6-detect-lots",
        "clear-match-data",
        "run-resumable-pipeline",
    ),
    "monitor.py": (
        "export-rankings",
        "match-stats",
        "monitor-pipeline",
        "list-stale-workflows",
        "clear-stale-workflows",
        "data-integrity-check",
    ),
}


def _rewrite(body: str) -> str:
    for old, new in (
        ("from .cli_context", "from ebay_workflows.cli_context"),
        ("from .config", "from ebay_workflows.config"),
        ("from .exceptions", "from ebay_workflows.exceptions"),
        ("from .hardening", "from ebay_workflows.hardening"),
        ("from .integrations", "from ebay_workflows.integrations"),
        ("from .services", "from ebay_workflows.services"),
        ("from .models", "from ebay_workflows.models"),
        ("from .pipeline_resume", "from ebay_workflows.pipeline_resume"),
    ):
        body = body.replace(old, new)
    for n in range(1, 7):
        body = body.replace(f"from .workflow_phase{n}", f"from ebay_workflows.workflow_phase{n}")
    return body


def main() -> None:
    text = CLI_FILE.read_text(encoding="utf-8")
    start = text.index('@app.command("validate-env")')
    commands_text = text[start:]
    commands_text = re.sub(r"\nif __name__ == .__main__.:\s*\n\s*app\(\)\s*$", "", commands_text)

    PKG.mkdir(exist_ok=True)
    CMD.mkdir(exist_ok=True)
    (PKG / "bootstrap.py").write_text(BOOTSTRAP, encoding="utf-8")

    parts = re.split(r"@app\.command\(", commands_text)
    by_name: dict[str, str] = {}
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        match = re.match(r'"([^"]+)"', stripped)
        if not match:
            continue
        by_name[match.group(1)] = "@app.command(" + part

    for fname, names in GROUPS.items():
        body = "".join(by_name[name] for name in names if name in by_name)
        (CMD / fname).write_text(COMMON + EXTRA[fname] + "\n" + _rewrite(body), encoding="utf-8")

    (CMD / "__init__.py").write_text(
        "from __future__ import annotations\n\n"
        "from . import env, index, ingest, monitor, phases\n\n"
        '__all__ = ["env", "index", "ingest", "monitor", "phases"]\n',
        encoding="utf-8",
    )
    (PKG / "__init__.py").write_text(
        "from __future__ import annotations\n\n"
        "from .bootstrap import app, console\n"
        "from . import commands  # noqa: F401\n\n"
        '__all__ = ["app", "console"]\n',
        encoding="utf-8",
    )
    CLI_FILE.unlink(missing_ok=True)
    print(f"Split CLI into {PKG} (removed {CLI_FILE.name})")


if __name__ == "__main__":
    main()
