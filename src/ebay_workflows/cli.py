from __future__ import annotations

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import OperationalError

from .config import Settings
from .db import build_engine, build_session_factory
from .integrations.cardmarket import load_cardmarket_bulk_rows
from .integrations.scryfall import sync_scryfall_bulk
from .models import Base
from .workflow_phase1 import run_phase1
from .workflow_phase2 import load_cards_from_cache, run_phase2_title_match, upsert_scryfall_cards
from .workflow_phase3 import run_phase3_join, sync_cardmarket_prices
from .workflow_phase4 import run_phase4_ranking
from .workflow_phase5 import run_phase5_ocr_verification

app = typer.Typer(help="EbayWorkflows local CLI.")
console = Console()


@app.command("validate-env")
def validate_env() -> None:
    """Validate env configuration and policy guardrails."""
    try:
        settings = Settings()
    except ValidationError as exc:
        console.print("[bold red]Environment validation failed.[/bold red]")
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", []))
            console.print(f"- {location}: {error.get('msg')}")
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        console.print(f"[bold red]Environment policy check failed:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    table = Table(title="Validated Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("APP_ENV", settings.app_env)
    table.add_row("BASE_CURRENCY", settings.base_currency)
    table.add_row("ENABLE_EBAY_API", str(settings.enable_ebay_api))
    table.add_row("EBAY_REQUESTS_PER_MINUTE", str(settings.ebay_requests_per_minute or "n/a"))
    table.add_row("SCRYFALL_REQUESTS_PER_MINUTE", str(settings.scryfall_requests_per_minute))
    table.add_row("CARDMARKET_BULK_FILE_PATH", settings.cardmarket_bulk_file_path)
    table.add_row("CARDMARKET_BULK_REFRESH_HOURS", str(settings.cardmarket_bulk_refresh_hours))
    table.add_row("GLOBAL_REQUESTS_PER_MINUTE_CAP", str(settings.global_requests_per_minute_cap))
    table.add_row("ENABLE_PROVIDER_POLICY_CHECKS", str(settings.enable_provider_policy_checks))
    table.add_row("DISABLE_LIVE_API_WRITES", str(settings.disable_live_api_writes))
    console.print(table)
    console.print("[bold green]Environment validation passed.[/bold green]")


@app.command("run")
def run_workflow(
    query: str = typer.Option(..., "--query", help="Search query to execute"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Avoid any write operations"),
    max_pages: int = typer.Option(1, "--max-pages", help="Max pages to fetch from provider"),
    mock_input_file: str | None = typer.Option(
        None,
        "--mock-input-file",
        help="Path to JSON file of listing records for local/offline ingestion",
    ),
    download_images: bool = typer.Option(
        False,
        "--download-images/--no-download-images",
        help="Download listing images into local cache",
    ),
) -> None:
    """Run Milestone 1 Phase 1 ingestion workflow."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start workflow:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    if not settings.enable_provider_policy_checks:
        console.print("[bold red]Policy checks must be enabled to run workflows.[/bold red]")
        raise typer.Exit(code=4)

    effective_dry_run = dry_run or settings.disable_live_api_writes
    if effective_dry_run:
        console.print("[bold]Workflow startup checks passed (dry run).[/bold]")
        console.print(f"Query: [cyan]{query}[/cyan]")
        console.print("No persistence executed in dry-run mode.")
        return

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        run_id = run_phase1(
            session=session,
            settings=settings,
            query=query,
            max_pages=max_pages,
            mock_input_file=mock_input_file,
            download_images=download_images,
        )
    console.print("[bold green]Phase 1 completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("init-db")
def init_db() -> None:
    """Create database tables for workflow storage."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot initialize DB:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    engine = build_engine(settings)
    try:
        Base.metadata.create_all(engine)
    except OperationalError as exc:
        console.print(f"[bold red]Database connection failed:[/bold red] {exc}")
        raise typer.Exit(code=5) from exc
    console.print("[bold green]Database schema initialized.[/bold green]")


@app.command("sync-scryfall")
def sync_scryfall() -> None:
    """Download and cache Scryfall bulk card data, then upsert DB records."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot sync Scryfall:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    cards = sync_scryfall_bulk(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        count = upsert_scryfall_cards(session, cards)
    console.print(f"[bold green]Scryfall sync complete.[/bold green] Loaded [cyan]{count}[/cyan] cards.")


@app.command("phase2-match-title")
def phase2_match_title(
    top_k: int = typer.Option(3, "--top-k", help="Top candidate cards retained per listing"),
) -> None:
    """Run Milestone 2 title-based listing to Scryfall matching."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start Phase 2:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        # Ensure local cache is present and structured before matching.
        load_cards_from_cache(settings)
        run_id = run_phase2_title_match(session, settings=settings, top_k=top_k)

    console.print("[bold green]Phase 2 title matching completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("sync-cardmarket")
def sync_cardmarket() -> None:
    """Load Cardmarket bulk pricing file into card_prices table."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot sync Cardmarket:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    load_cardmarket_bulk_rows(settings.cardmarket_bulk_file_path)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        count = sync_cardmarket_prices(session, settings)
    console.print(f"[bold green]Cardmarket sync complete.[/bold green] Loaded [cyan]{count}[/cyan] prices.")


@app.command("phase3-join-prices")
def phase3_join_prices() -> None:
    """Run Milestone 3 Cardmarket price join for matched candidates."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start Phase 3:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        run_id = run_phase3_join(session, settings)
    console.print("[bold green]Phase 3 price join completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("phase4-rank")
def phase4_rank() -> None:
    """Run Milestone 4 EV/confidence scoring and ranking."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start Phase 4:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        run_id = run_phase4_ranking(session, settings)
    console.print("[bold green]Phase 4 ranking completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("phase5-verify-ocr")
def phase5_verify_ocr(
    mock_ocr_file: str = typer.Option(
        ...,
        "--mock-ocr-file",
        help="Path to JSON mock OCR evidence file for deterministic verification",
    ),
) -> None:
    """Run Milestone 5 OCR verification to refine candidate confidence."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start Phase 5:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        run_id = run_phase5_ocr_verification(session, settings, mock_ocr_file=mock_ocr_file)
    console.print("[bold green]Phase 5 OCR verification completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


if __name__ == "__main__":
    app()

