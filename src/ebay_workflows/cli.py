from __future__ import annotations

import os
from pathlib import Path

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table
from sqlalchemy.exc import OperationalError

from .config import Settings
from .db import build_engine, build_session_factory
from .hardening import run_data_integrity_checks
from .integrations.cardmarket import load_cardmarket_bulk_rows
from .integrations.cardmarket_bulk import download_and_build_singles_csv
from .integrations.ebay import verify_ebay_credentials
from .integrations.scryfall import sync_scryfall_bulk
from .services.embedding_index import build_faiss_index
from .services.ranked_export import fetch_ranked_listings, write_ranked_json
from .models import Base
from .pipeline_resume import ResumablePipelineConfig, run_resumable_pipeline
from .workflow_phase1 import run_phase1
from .workflow_phase2 import load_cards_from_cache, run_phase2_title_match, upsert_scryfall_cards
from .workflow_phase3 import run_phase3_join, sync_cardmarket_prices
from .workflow_phase4 import run_phase4_ranking
from .workflow_phase5 import run_phase5_ocr_verification
from .workflow_phase6 import run_phase6_bulk_lot_detection

app = typer.Typer(help="EbayWorkflows local CLI.")
console = Console()

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

    _warn_shell_env_overrides()

    table = Table(title="Validated Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("APP_ENV", settings.app_env)
    table.add_row("BASE_CURRENCY", settings.base_currency)
    table.add_row("ENABLE_EBAY_API", str(settings.enable_ebay_api))
    table.add_row("EBAY_USE_SANDBOX", str(settings.ebay_use_sandbox))
    table.add_row("EBAY_CLIENT_ID (production)", "set" if settings.ebay_client_id else "not set")
    table.add_row("EBAY_SANDBOX_CLIENT_ID", "set" if settings.ebay_sandbox_client_id else "not set")
    table.add_row(
        "Active eBay credentials",
        "sandbox" if settings.ebay_use_sandbox else "production",
    )
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


@app.command("ebay-auth-check")
def ebay_auth_check() -> None:
    """Verify eBay OAuth credentials without running ingestion."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot verify eBay auth:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    try:
        token = verify_ebay_credentials(settings)
    except ValueError as exc:
        console.print(f"[bold red]eBay authentication failed:[/bold red] {exc}")
        raise typer.Exit(code=7) from exc

    env_label = "sandbox" if settings.ebay_use_sandbox else "production"
    console.print(f"[bold green]eBay OAuth succeeded[/bold green] ({env_label}).")
    console.print(f"Token prefix: [cyan]{token[:12]}...[/cyan]")


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


@app.command("build-faiss-index")
def build_faiss_index_cmd(
    max_cards: int | None = typer.Option(
        None,
        "--max-cards",
        help="Max Scryfall cards to index (defaults to FAISS_BUILD_MAX_CARDS)",
    ),
) -> None:
    """Build OpenCLIP + FAISS index from Scryfall card art."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot build FAISS index:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    limit = max_cards if max_cards is not None else settings.faiss_build_max_cards
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = build_faiss_index(session, settings, max_cards=limit)

    table = Table(title="FAISS Index Build Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    for key, value in summary.items():
        table.add_row(key, str(value))
    console.print(table)
    console.print("[bold green]FAISS index build complete.[/bold green]")


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


@app.command("download-cardmarket-bulk")
def download_cardmarket_bulk(
    output: str = typer.Option(
        "./data/cardmarket/prices.csv",
        "--output",
        "-o",
        help="Path for normalized CSV used by sync-cardmarket",
    ),
    cache_dir: str = typer.Option(
        "./data/cardmarket",
        "--cache-dir",
        help="Directory for raw Cardmarket JSON exports",
    ),
    price_field: str = typer.Option(
        "trend",
        "--price-field",
        help="Cardmarket price column: trend, low, avg, avg7, avg30, low-foil, trend-foil",
    ),
    force: bool = typer.Option(False, "--force", help="Re-download JSON even if cached"),
) -> None:
    """Download official Cardmarket MTG singles price guide and build normalized CSV."""
    try:
        meta = download_and_build_singles_csv(
            output,
            cache_dir=cache_dir,
            price_field=price_field,
            force_download=force,
        )
    except (httpx.HTTPError, ValueError, OSError) as exc:
        console.print(f"[bold red]Cardmarket download failed:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    console.print("[bold green]Cardmarket bulk CSV ready.[/bold green]")
    console.print(f"Output: [cyan]{meta['output_csv']}[/cyan]")
    console.print(f"Rows: [cyan]{meta['rows_written']}[/cyan] (from {meta['products_count']} singles)")
    console.print(f"Price field: [cyan]{meta['price_field']}[/cyan]")
    console.print("Set CARDMARKET_BULK_FILE_PATH to this file, then run sync-cardmarket.")


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
def phase4_rank(
    hybrid: bool = typer.Option(
        True,
        "--hybrid/--no-hybrid",
        help="Use v2 hybrid confidence (title + OCR + embedding + price freshness)",
    ),
) -> None:
    """Run Milestone 4 EV/confidence scoring and ranking."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start Phase 4:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        run_id = run_phase4_ranking(session, settings, use_hybrid=hybrid)
    console.print("[bold green]Phase 4 ranking completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("export-rankings")
def export_rankings(
    limit: int = typer.Option(25, "--limit", help="Max ranked listings to export"),
    output: str | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write ranked results to JSON file (e.g. ./data/exports/ranked.json)",
    ),
) -> None:
    """Export ranked listings as a Rich table and optional JSON file."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot export rankings:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        rows = fetch_ranked_listings(session, limit=limit)

    if not rows:
        console.print("[yellow]No ranked listings found. Run phase4-rank first.[/yellow]")
        raise typer.Exit(code=3)

    table = Table(title=f"Top {len(rows)} Ranked Listings")
    table.add_column("Rank", style="cyan", justify="right")
    table.add_column("EV Adj", style="green", justify="right")
    table.add_column("Conf", justify="right")
    table.add_column("Title", style="white")
    table.add_column("Top Card", style="magenta")
    table.add_column("Price", justify="right")

    for row in rows:
        price = f"{row.price_amount:.2f} {row.currency}"
        table.add_row(
            str(row.rank),
            f"{row.ev_adjusted:.2f}",
            f"{row.confidence_score:.2f}",
            row.title[:48] + ("…" if len(row.title) > 48 else ""),
            (row.top_card_name or "—")[:24],
            price,
        )
    console.print(table)

    if output:
        path = write_ranked_json(rows, output)
        console.print(f"[bold green]JSON export written:[/bold green] [cyan]{path}[/cyan]")


@app.command("phase5-verify-ocr")
def phase5_verify_ocr(
    mock_ocr_file: str = typer.Option(
        None,
        "--mock-ocr-file",
        help="Path to JSON mock OCR evidence file for deterministic verification",
    ),
    use_real_ocr: bool = typer.Option(
        False,
        "--use-real-ocr/--no-use-real-ocr",
        help="Use OpenCV + Tesseract OCR from local image files when no mock file is supplied",
    ),
    use_embedding_match: bool = typer.Option(
        False,
        "--use-embedding-match/--no-use-embedding-match",
        help="Run OpenCLIP+FAISS similarity on crops when index exists",
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
        run_id = run_phase5_ocr_verification(
            session,
            settings,
            mock_ocr_file=mock_ocr_file,
            use_real_ocr=use_real_ocr,
            use_embedding_match=use_embedding_match,
        )
    console.print("[bold green]Phase 5 OCR verification completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("phase6-detect-lots")
def phase6_detect_lots(
    mock_lot_file: str | None = typer.Option(
        None,
        "--mock-lot-file",
        help="Path to JSON mock bulk-lot detections for deterministic execution",
    ),
    use_real_detection: bool = typer.Option(
        False,
        "--use-real-detection/--no-use-real-detection",
        help="Detect multiple cards per image with OpenCV + OCR on local listing images",
    ),
) -> None:
    """Run Milestone 6 bulk-lot multi-card detection and EV adjustment."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start Phase 6:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        run_id = run_phase6_bulk_lot_detection(
            session,
            settings,
            mock_lot_file=mock_lot_file,
            use_real_detection=use_real_detection,
        )
    console.print("[bold green]Phase 6 bulk-lot detection completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("data-integrity-check")
def data_integrity_check() -> None:
    """Run post-MVP data integrity checks for pipeline hardening."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot run integrity checks:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        report = run_data_integrity_checks(session)

    if report.issues_found:
        console.print(
            f"[bold red]Integrity checks failed.[/bold red] "
            f"Issues: [cyan]{report.issues_found}[/cyan] / Checks: [cyan]{report.checks_run}[/cyan]"
        )
        for issue in report.details:
            console.print(f"- {issue}")
        raise typer.Exit(code=6)

    console.print(
        "[bold green]Integrity checks passed.[/bold green] "
        f"Checks run: [cyan]{report.checks_run}[/cyan]"
    )


@app.command("run-resumable-pipeline")
def run_resumable_pipeline_cmd(
    query: str = typer.Option("mtg lot", "--query", help="Search query for phase 1 ingestion"),
    max_pages: int = typer.Option(1, "--max-pages", help="Max pages to fetch in phase 1"),
    mock_input_file: str | None = typer.Option(
        None,
        "--mock-input-file",
        help="Path to JSON file for phase 1 offline ingestion",
    ),
    download_images: bool = typer.Option(
        False,
        "--download-images/--no-download-images",
        help="Download listing images in phase 1",
    ),
    top_k: int = typer.Option(3, "--top-k", help="Top candidate cards retained in phase 2"),
    mock_ocr_file: str | None = typer.Option(
        None,
        "--mock-ocr-file",
        help="Mock OCR file used by phase 5",
    ),
    use_real_ocr: bool = typer.Option(
        False,
        "--use-real-ocr/--no-use-real-ocr",
        help="Use real OCR for phase 5 when no mock OCR file is provided",
    ),
    mock_lot_file: str | None = typer.Option(
        None,
        "--mock-lot-file",
        help="Mock lot detection file used by phase 6",
    ),
    use_real_lot_detection: bool = typer.Option(
        False,
        "--use-real-lot-detection/--no-use-real-lot-detection",
        help="Use OpenCV bulk-lot detection for phase 6",
    ),
    from_phase: int = typer.Option(1, "--from-phase", min=1, max=6, help="First phase to execute"),
    to_phase: int = typer.Option(6, "--to-phase", min=1, max=6, help="Last phase to execute"),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="Skip already-complete phases based on persisted data",
    ),
) -> None:
    """Run phases 1-6 with replay/resume safety and phase skipping."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start resumable pipeline:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    cfg = ResumablePipelineConfig(
        query=query,
        max_pages=max_pages,
        mock_input_file=mock_input_file,
        download_images=download_images,
        top_k=top_k,
        mock_ocr_file=mock_ocr_file,
        use_real_ocr=use_real_ocr,
        mock_lot_file=mock_lot_file,
        use_real_lot_detection=use_real_lot_detection,
        from_phase=from_phase,
        to_phase=to_phase,
        resume=resume,
    )

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = run_resumable_pipeline(session, settings, cfg)

    table = Table(title="Resumable Pipeline Result")
    table.add_column("Type", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Executed", str(summary.get("executed", {})))
    table.add_row("Skipped phases", str(summary.get("skipped", [])))
    console.print(table)


if __name__ == "__main__":
    app()

