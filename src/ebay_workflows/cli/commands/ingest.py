from __future__ import annotations

import httpx
import typer
from rich.table import Table

from ebay_workflows.cli.bootstrap import app, console
from ebay_workflows.cli_context import cli_session, load_settings

from ebay_workflows.services.ingest_helpers import resolve_max_pages
from ebay_workflows.workflow_phase1 import retry_failed_image_downloads, run_phase1
from ebay_workflows.integrations.scryfall import sync_scryfall_bulk
from ebay_workflows.workflow_phase2 import upsert_scryfall_cards
from ebay_workflows.integrations.cardmarket import load_cardmarket_bulk_rows
from ebay_workflows.workflow_phase3 import sync_cardmarket_prices
from ebay_workflows.integrations.cardmarket_bulk import download_and_build_singles_csv

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
    settings = load_settings(action="start workflow")

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

    with cli_session(action="start workflow", settings=settings) as (_, session):
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


@app.command("retry-failed-images")
def retry_failed_images_cmd() -> None:
    """Re-download listing images that are failed or still pending from Phase 1."""
    with cli_session(action="retry images") as (settings, session):
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
    settings = load_settings(action="sync Scryfall")
    cards = sync_scryfall_bulk(settings)
    with cli_session(action="sync Scryfall", settings=settings) as (_, session):
        count = upsert_scryfall_cards(session, cards)
    console.print(f"[bold green]Scryfall sync complete.[/bold green] Loaded [cyan]{count}[/cyan] cards.")


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
    settings = load_settings(action="sync Cardmarket")
    load_cardmarket_bulk_rows(settings.cardmarket_bulk_file_path)
    with cli_session(action="sync Cardmarket", settings=settings) as (_, session):
        count = sync_cardmarket_prices(session, settings)
    console.print(f"[bold green]Cardmarket sync complete.[/bold green] Loaded [cyan]{count}[/cyan] prices.")


