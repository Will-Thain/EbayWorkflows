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
from .services.embedding_index import (
    append_faiss_batch,
    build_faiss_index,
    build_faiss_index_all_batches,
    count_indexable_art_cards,
    index_exists,
    indexed_scryfall_ids,
)
from .services.set_symbol_match import build_set_symbol_templates, set_symbol_template_dir
from .services.health_checks import collect_operational_health
from .services.ingest_helpers import max_listings_per_query, resolve_max_pages
from .services.clear_matching_data import clear_matching_artifacts, count_matching_artifacts
from .services.ranked_export import fetch_ranked_listings, write_ranked_json
from .models import Base
from .pipeline_resume import ResumablePipelineConfig, run_resumable_pipeline
from .workflow_phase1 import retry_failed_image_downloads, run_phase1
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
    table.add_row("EBAY_PAGE_SIZE", str(settings.ebay_page_size))
    table.add_row("EBAY_MAX_PAGES_PER_RUN", str(settings.ebay_max_pages_per_run))
    table.add_row(
        "Max listings per query (cap)",
        str(max_listings_per_query(settings, settings.ebay_max_pages_per_run)),
    )
    table.add_row("PHASE1_COMMIT_BATCH_SIZE", str(settings.phase1_commit_batch_size))
    table.add_row("PHASE1_SKIP_EXISTING_LISTINGS", str(settings.phase1_skip_existing_listings))
    table.add_row("PHASE1_REFRESH_AFTER_HOURS", str(settings.phase1_refresh_after_hours or "disabled"))
    table.add_row("FX_GBP_TO_EUR", str(settings.fx_gbp_to_eur or "n/a"))
    table.add_row("PHASE5_SKIP_ANALYZED_IMAGES", str(settings.phase5_skip_analyzed_images))
    table.add_row("PIPELINE_ENFORCE_SINGLE_RUN", str(settings.pipeline_enforce_single_run))
    faiss_ready = index_exists(settings.faiss_index_path)
    table.add_row("FAISS_INDEX_PATH", settings.faiss_index_path)
    table.add_row("FAISS_INDEX_READY", "yes" if faiss_ready else "no — run build-faiss-index")
    table.add_row("FAISS_BUILD_MAX_CARDS", str(settings.faiss_build_max_cards))
    table.add_row("FAISS_INDEX_USE_ART_ZONE", str(settings.faiss_index_use_art_zone))
    table.add_row("FAISS_BUILD_ALL_CARDS", str(settings.faiss_build_all_cards))
    table.add_row("SCRYFALL_REQUESTS_PER_MINUTE", str(settings.scryfall_requests_per_minute))
    table.add_row("CARDMARKET_BULK_FILE_PATH", settings.cardmarket_bulk_file_path)
    table.add_row("CARDMARKET_BULK_REFRESH_HOURS", str(settings.cardmarket_bulk_refresh_hours))
    table.add_row("GLOBAL_REQUESTS_PER_MINUTE_CAP", str(settings.global_requests_per_minute_cap))
    table.add_row("ENABLE_PROVIDER_POLICY_CHECKS", str(settings.enable_provider_policy_checks))
    table.add_row("DISABLE_LIVE_API_WRITES", str(settings.disable_live_api_writes))
    table.add_row("TORCH_DEVICE", settings.torch_device)
    table.add_row("EMBEDDING_BATCH_SIZE", str(settings.embedding_batch_size))
    table.add_row("PIPELINE_MAX_IMAGE_WORKERS", str(settings.pipeline_max_image_workers))
    table.add_row("PIPELINE_MAX_DOWNLOAD_WORKERS", str(settings.pipeline_max_download_workers))
    table.add_row("PIPELINE_MAX_TITLE_MATCH_WORKERS", str(settings.pipeline_max_title_match_workers))
    table.add_row("TITLE_MATCH_PREFILTER_SIZE", str(settings.title_match_prefilter_size))
    table.add_row("TITLE_MATCH_SCORE_CUTOFF", str(settings.title_match_score_cutoff))
    table.add_row("PHASE6_USE_FAISS_CROP_MATCH", str(settings.phase6_use_faiss_crop_match))
    table.add_row("CARD_ZONE_OCR_ENABLED", str(settings.card_zone_ocr_enabled))
    table.add_row("CARD_ZONE_FAISS_ENABLED", str(settings.card_zone_faiss_enabled))
    table.add_row("CARD_ZONE_ALIGN_ENABLED", str(settings.card_zone_align_enabled))
    table.add_row("CARD_SET_SYMBOL_MATCH_ENABLED", str(settings.card_set_symbol_match_enabled))
    table.add_row("IMAGE_EVIDENCE_MIN_FAISS_SCORE", str(settings.image_evidence_min_faiss_score))
    table.add_row("IMAGE_EVIDENCE_MIN_MANA_CONFIDENCE", str(settings.image_evidence_min_mana_confidence))
    table.add_row("PHASE2_SKIP_UNCHANGED_LISTINGS", str(settings.phase2_skip_unchanged_listings))
    console.print(table)

    try:
        session_factory = build_session_factory(settings)
        with session_factory() as session:
            health = collect_operational_health(session, settings)
        warn_table = Table(title="Operational Health")
        warn_table.add_column("Check", style="cyan")
        warn_table.add_column("Status", style="yellow")
        warnings_added = 0
        if health.get("faiss_index_incomplete"):
            warnings_added += 1
            warn_table.add_row(
                "FAISS index",
                f"incomplete ({health['faiss_vector_count']}/{health['faiss_build_max_cards']} vectors)",
            )
        if health.get("cardmarket_bulk_stale"):
            warnings_added += 1
            warn_table.add_row(
                "Cardmarket bulk",
                f"stale ({health['cardmarket_bulk_age_hours']:.1f}h old)",
            )
        if health.get("cardmarket_bulk_missing"):
            warnings_added += 1
            warn_table.add_row("Cardmarket bulk", "missing — run download-cardmarket-bulk")
        if health.get("failed_image_downloads", 0) > 0:
            warnings_added += 1
            warn_table.add_row(
                "Failed images",
                f"{health['failed_image_downloads']} — run retry-failed-images",
            )
        if health.get("faiss_index_crop_mismatch"):
            warnings_added += 1
            warn_table.add_row(
                "FAISS crop mode",
                f"index={health.get('faiss_indexed_crop_mode')} vs config={health.get('faiss_index_crop_mode')} — rebuild with build-faiss-index",
            )
        if health.get("set_symbol_templates_missing"):
            warnings_added += 1
            warn_table.add_row(
                "Set symbol templates",
                f"low count ({health.get('set_symbol_template_count', 0)}) — run build-set-symbol-templates",
            )
        if warnings_added:
            console.print(warn_table)
    except OperationalError:
        console.print("[yellow]Operational health checks skipped (database unavailable).[/yellow]")

    console.print("[bold green]Environment validation passed.[/bold green]")


@app.command("run")
def run_workflow(
    query: str = typer.Option(..., "--query", help="Search query to execute"),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Avoid any write operations"),
    max_pages: int | None = typer.Option(
        None,
        "--max-pages",
        help="Max pages to fetch (default: EBAY_MAX_PAGES_PER_RUN from .env)",
    ),
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
    queries_file: str | None = typer.Option(
        None,
        "--queries-file",
        help="Text file with one eBay search query per line (rotates past 10k offset cap)",
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

    pages = resolve_max_pages(max_pages, settings)
    console.print(f"Fetching up to [cyan]{pages}[/cyan] pages ({settings.ebay_page_size} items/page).")

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        run_id = run_phase1(
            session=session,
            settings=settings,
            query=query,
            max_pages=pages,
            mock_input_file=mock_input_file,
            download_images=download_images,
            queries_file=queries_file,
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
        indexes = ensure_performance_indexes(engine)
    except OperationalError as exc:
        console.print(f"[bold red]Database connection failed:[/bold red] {exc}")
        raise typer.Exit(code=5) from exc
    console.print("[bold green]Database schema initialized.[/bold green]")
    if indexes:
        console.print(f"Performance indexes ensured ({len(indexes)}).")


@app.command("ensure-db-indexes")
def ensure_db_indexes() -> None:
    """Create idempotent performance indexes on an existing database."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot ensure indexes:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    engine = build_engine(settings)
    try:
        indexes = ensure_performance_indexes(engine)
    except OperationalError as exc:
        console.print(f"[bold red]Database connection failed:[/bold red] {exc}")
        raise typer.Exit(code=5) from exc
    console.print(f"[bold green]Performance indexes ensured ({len(indexes)}).[/bold green]")


@app.command("retry-failed-images")
def retry_failed_images_cmd() -> None:
    """Re-download listing images that are failed or still pending from Phase 1."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot retry images:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        metrics = retry_failed_image_downloads(session, settings)

    table = Table(title="Image Retry Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    for key, value in metrics.items():
        table.add_row(key, str(value))
    console.print(table)


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


@app.command("build-set-symbol-templates")
def build_set_symbol_templates_cmd() -> None:
    """Build set-symbol template images from Scryfall reference art (one per set)."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot build set symbol templates:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        metrics = build_set_symbol_templates(session, settings)

    table = Table(title="Set Symbol Templates")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    for key, value in metrics.items():
        table.add_row(key, str(value))
    console.print(table)
    console.print(
        f"[bold green]Templates directory:[/bold green] {set_symbol_template_dir(settings)}"
    )


@app.command("build-faiss-index")
def build_faiss_index_cmd(
    max_cards: int | None = typer.Option(
        None,
        "--max-cards",
        help="Max Scryfall cards to index (defaults to FAISS_BUILD_MAX_CARDS)",
    ),
    append: bool = typer.Option(
        False,
        "--append/--replace",
        help="Append next batch to existing index instead of replacing it",
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
        if append:
            summary = append_faiss_batch(session, settings, batch_size=limit)
        else:
            summary = build_faiss_index(session, settings, max_cards=limit)

    table = Table(title="FAISS Index Build Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    for key, value in summary.items():
        table.add_row(key, str(value))
    console.print(table)
    console.print("[bold green]FAISS index build complete.[/bold green]")


@app.command("build-faiss-index-batches")
def build_faiss_index_batches_cmd(
    batch_size: int | None = typer.Option(
        None,
        "--batch-size",
        help="Cards per batch (defaults to FAISS_BUILD_MAX_CARDS)",
    ),
    max_batches: int | None = typer.Option(
        None,
        "--max-batches",
        help="Stop after N batches (default: run until all indexable art is embedded)",
    ),
) -> None:
    """Append FAISS batches until all Scryfall art cards are indexed."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot build FAISS batches:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    batch = batch_size if batch_size is not None else settings.faiss_build_max_cards
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        already = len(indexed_scryfall_ids(settings.faiss_index_path))
        total = count_indexable_art_cards(session)
        console.print(
            f"Starting batched FAISS build: [cyan]{already}[/cyan] / [cyan]{total}[/cyan] "
            f"vectors indexed; batch size [cyan]{batch}[/cyan]."
        )
        summary = build_faiss_index_all_batches(
            session,
            settings,
            batch_size=batch,
            max_batches=max_batches,
        )

    table = Table(title="FAISS Batch Build Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    for key, value in summary.items():
        table.add_row(key, str(value))
    console.print(table)
    if summary.get("complete"):
        console.print("[bold green]Full FAISS index build complete.[/bold green]")
    else:
        console.print("[bold yellow]Batch limit reached; index still incomplete.[/bold yellow]")


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


@app.command("clear-match-data")
def clear_match_data(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    keep_exports: bool = typer.Option(False, "--keep-exports", help="Do not delete ranked export JSON files"),
) -> None:
    """Delete title/image match artifacts and scores; keep listings, images, Scryfall, and prices."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot clear match data:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        before = count_matching_artifacts(session)

    table = Table(title="Match data to delete")
    table.add_column("Table / artifact", style="cyan")
    table.add_column("Rows / files", style="yellow")
    for key, value in before.items():
        table.add_row(key, str(value))
    console.print(table)

    if sum(before.values()) == 0 and keep_exports:
        console.print("[green]No match data found in the database.[/green]")
        return

    if not yes and not typer.confirm("Delete all match/score data listed above?", default=False):
        console.print("[yellow]Aborted.[/yellow]")
        raise typer.Exit(code=1)

    with session_factory() as session:
        report = clear_matching_artifacts(
            session,
            export_dir=None if keep_exports else "./data/exports",
        )

    result = Table(title="Cleared match data")
    result.add_column("Artifact", style="cyan")
    result.add_column("Deleted", style="green")
    result.add_row("ocr_results", str(report.ocr_results_deleted))
    result.add_row("image_detections", str(report.image_detections_deleted))
    result.add_row("listing_card_candidates", str(report.listing_candidates_deleted))
    result.add_row("listing_scores", str(report.listing_scores_deleted))
    if not keep_exports:
        result.add_row("ranked export files", str(report.export_files_deleted))
    console.print(result)
    console.print(
        "[bold green]Match data cleared.[/bold green] "
        "Listings and downloaded images were kept. Run [cyan]./scripts/reanalyze-matching.ps1[/cyan] next."
    )


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
    max_pages: int | None = typer.Option(
        None,
        "--max-pages",
        help="Max pages to fetch in phase 1 (default: EBAY_MAX_PAGES_PER_RUN)",
    ),
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

    pages = resolve_max_pages(max_pages, settings)
    cfg = ResumablePipelineConfig(
        query=query,
        max_pages=pages,
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

