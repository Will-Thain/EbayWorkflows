from __future__ import annotations

import typer
from pydantic import ValidationError
from rich.table import Table
from sqlalchemy.exc import OperationalError

from ebay_workflows.cli.bootstrap import app, console, _warn_shell_env_overrides
from ebay_workflows.cli_context import cli_engine, cli_session, load_settings
from ebay_workflows.config import Settings
from ebay_workflows.exceptions import AuthenticationError, ConfigurationError

from ebay_workflows.models import Base
from ebay_workflows.services.db_indexes import ensure_performance_indexes
from ebay_workflows.integrations.ebay import verify_ebay_credentials
from ebay_workflows.services.health_checks import collect_operational_health
from ebay_workflows.services.embedding_index import index_exists
from ebay_workflows.services.ingest_helpers import max_listings_per_query

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
    table.add_row("FAISS_INDEX_READY", "yes" if faiss_ready else "no ÔÇö run build-faiss-index")
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
    table.add_row("ALIGN_MIN_CONFIDENCE", str(settings.align_min_confidence))
    table.add_row("VERIFY_NAME_HARD_MIN", str(settings.verify_name_hard_min))
    table.add_row("VERIFY_NAME_STRONG_MIN", str(settings.verify_name_strong_min))
    table.add_row("VERIFY_SYMBOL_STRONG_MIN", str(settings.verify_symbol_strong_min))
    table.add_row("FAISS_PROPOSE_CANDIDATES", str(settings.faiss_propose_candidates))
    table.add_row("PHASE2_SKIP_UNCHANGED_LISTINGS", str(settings.phase2_skip_unchanged_listings))
    console.print(table)

    try:
        with cli_session(action="load settings", settings=settings) as (_, session):
            health = collect_operational_health(session, settings)
        match_stats = health.get("match_stats") or {}
        if match_stats:
            stats_table = Table(title="Match Statistics")
            stats_table.add_column("Metric", style="cyan")
            stats_table.add_column("Count", style="green", justify="right")
            stats_table.add_row("Verified listings", str(match_stats.get("verified_listings", 0)))
            stats_table.add_row("Pricing-eligible candidates", str(match_stats.get("pricing_eligible_candidates", 0)))
            stats_table.add_row("Listings with rank_value > 0", str(match_stats.get("listings_with_positive_rank", 0)))
            sources = match_stats.get("verification_source_counts") or {}
            if sources:
                for source, count in sorted(sources.items()):
                    stats_table.add_row(f"  verified via {source}", str(count))
            console.print(stats_table)
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
            warn_table.add_row("Cardmarket bulk", "missing ÔÇö run download-cardmarket-bulk")
        if health.get("failed_image_downloads", 0) > 0:
            warnings_added += 1
            warn_table.add_row(
                "Failed images",
                f"{health['failed_image_downloads']} ÔÇö run retry-failed-images",
            )
        if health.get("faiss_index_crop_mismatch"):
            warnings_added += 1
            warn_table.add_row(
                "FAISS crop mode",
                f"index={health.get('faiss_indexed_crop_mode')} vs config={health.get('faiss_index_crop_mode')} ÔÇö rebuild with build-faiss-index",
            )
        if health.get("set_symbol_templates_missing"):
            warnings_added += 1
            warn_table.add_row(
                "Set symbol templates",
                f"low count ({health.get('set_symbol_template_count', 0)}) ÔÇö run build-set-symbol-templates",
            )
        if health.get("verify_thresholds_invalid"):
            warnings_added += 1
            keys = ", ".join(health.get("invalid_threshold_keys", []))
            warn_table.add_row(
                "Verify thresholds",
                f"out of range (0, 1]: {keys}",
            )
        if warnings_added:
            console.print(warn_table)
    except OperationalError:
        console.print("[yellow]Operational health checks skipped (database unavailable).[/yellow]")

    console.print("[bold green]Environment validation passed.[/bold green]")


@app.command("ebay-auth-check")
def ebay_auth_check() -> None:
    """Verify eBay OAuth credentials without running ingestion."""
    settings = load_settings(action="verify eBay auth")

    try:
        token = verify_ebay_credentials(settings)
    except (AuthenticationError, ConfigurationError, ValueError) as exc:
        console.print(f"[bold red]eBay authentication failed:[/bold red] {exc}")
        raise typer.Exit(code=7) from exc

    env_label = "sandbox" if settings.ebay_use_sandbox else "production"
    console.print(f"[bold green]eBay OAuth succeeded[/bold green] ({env_label}).")
    console.print(f"Token prefix: [cyan]{token[:12]}...[/cyan]")


@app.command("init-db")
def init_db() -> None:
    """Create database tables for workflow storage."""
    with cli_engine(action="initialize DB") as (_, engine):
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
    with cli_engine(action="ensure indexes") as (_, engine):
        try:
            indexes = ensure_performance_indexes(engine)
        except OperationalError as exc:
            console.print(f"[bold red]Database connection failed:[/bold red] {exc}")
            raise typer.Exit(code=5) from exc
    console.print(f"[bold green]Performance indexes ensured ({len(indexes)}).[/bold green]")


