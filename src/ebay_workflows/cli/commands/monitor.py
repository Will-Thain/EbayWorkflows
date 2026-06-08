from __future__ import annotations

import typer
from rich.table import Table

from ebay_workflows.cli.bootstrap import app, console
from ebay_workflows.cli_context import cli_session, load_settings

from ebay_workflows.hardening import run_data_integrity_checks
from ebay_workflows.services.match_stats import collect_match_stats
from ebay_workflows.services.pipeline_progress import collect_pipeline_progress
from ebay_workflows.services.stale_workflows import clear_stale_workflow_steps, list_running_workflow_views
from ebay_workflows.services.ranked_export import fetch_ranked_listings, write_ranked_json

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
    with cli_session(action="export rankings") as (_, session):
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
            row.title[:48] + ("ÔÇª" if len(row.title) > 48 else ""),
            (row.top_card_name or "ÔÇö")[:24],
            price,
        )
    console.print(table)

    if output:
        path = write_ranked_json(rows, output)
        console.print(f"[bold green]JSON export written:[/bold green] [cyan]{path}[/cyan]")


@app.command("match-stats")
def match_stats() -> None:
    """Print verification and ranking counts from the current database."""
    with cli_session(action="load settings") as (_, session):
        stats = collect_match_stats(session)

    table = Table(title="Match Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_row("Listings", str(stats["total_listings"]))
    table.add_row("Card candidates", str(stats["total_candidates"]))
    table.add_row("Scored listings", str(stats["scored_listings"]))
    table.add_row("Verified listings (distinct)", str(stats["verified_listings"]))
    table.add_row("Verified candidates", str(stats["verified_candidates"]))
    table.add_row("Pricing-eligible candidates", str(stats["pricing_eligible_candidates"]))
    table.add_row("Listings with rank_value > 0", str(stats["listings_with_positive_rank"]))
    console.print(table)

    sources = stats.get("verification_source_counts") or {}
    if sources:
        src_table = Table(title="Verification sources (image_verified=true)")
        src_table.add_column("Source", style="cyan")
        src_table.add_column("Count", style="green", justify="right")
        for source, count in sorted(sources.items()):
            src_table.add_row(source, str(count))
        console.print(src_table)
    else:
        console.print("[yellow]No verified candidates in database yet.[/yellow]")


@app.command("monitor-pipeline")
def monitor_pipeline() -> None:
    """Print read-only pipeline table counts (listings, images, OCR, match stats)."""
    with cli_session(action="load settings") as (_, session):
        stats = collect_pipeline_progress(session)

    table = Table(title="Pipeline Progress")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")
    for key, label in (
        ("total_listings", "Listings"),
        ("listing_images", "Listing images"),
        ("image_detections", "Image detections"),
        ("lot_detections", "Lot card detections"),
        ("ocr_results", "OCR results"),
        ("total_candidates", "Card candidates"),
        ("verified_candidates", "Verified candidates"),
        ("pricing_eligible_candidates", "Pricing-eligible candidates"),
        ("scored_listings", "Scored listings"),
        ("listings_with_positive_rank", "Listings rank_value > 0"),
    ):
        table.add_row(label, str(stats.get(key, 0)))
    console.print(table)


@app.command("list-stale-workflows")
def list_stale_workflows() -> None:
    """List workflow_steps stuck in running (live vs stale)."""
    settings = load_settings(action="load settings")
    with cli_session(action="load settings", settings=settings) as (_, session):
        views = list_running_workflow_views(
            session,
            local_job_id=None,
            runner_busy=False,
            lock_path=settings.pipeline_lock_path,
        )

    if not views:
        console.print("[green]No workflow steps with status=running.[/green]")
        return

    table = Table(title="Running workflow steps")
    table.add_column("State", style="cyan")
    table.add_column("Job", style="cyan")
    table.add_column("Step")
    table.add_column("Age", justify="right")
    table.add_column("Reason")
    for view in views:
        style = "red" if view.lifecycle == "stale" else "green"
        table.add_row(
            f"[{style}]{view.lifecycle.upper()}[/{style}]",
            view.job_id,
            view.step_name,
            view.age_label,
            view.reason,
        )
    console.print(table)


@app.command("clear-stale-workflows")
def clear_stale_workflows_cmd(
    yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
) -> None:
    """Mark stale running workflow steps as failed (unblocks pipeline mutex)."""
    settings = load_settings(action="load settings")
    with cli_session(action="load settings", settings=settings) as (_, session):
        views = list_running_workflow_views(
            session,
            local_job_id=None,
            runner_busy=False,
            lock_path=settings.pipeline_lock_path,
        )
        stale_ids = [view.step_id for view in views if view.can_clear]
        if not stale_ids:
            console.print("[green]No stale running workflows to clear.[/green]")
            return
        if not yes:
            console.print(f"Would clear {len(stale_ids)} stale step(s). Re-run with --yes to apply.")
            raise typer.Exit(code=1)
        result = clear_stale_workflow_steps(
            session,
            stale_ids,
            lock_path=settings.pipeline_lock_path,
        )

    console.print(
        f"[bold green]Cleared {result.cleared_steps} stale workflow step(s).[/bold green]"
    )


@app.command("data-integrity-check")
def data_integrity_check() -> None:
    """Run post-MVP data integrity checks for pipeline hardening."""
    with cli_session(action="run integrity checks") as (_, session):
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


@app.command("prune-image-cache")
def prune_image_cache(
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--execute",
        help="Report orphan files without deleting (default) or remove them",
    ),
) -> None:
    """Remove unreferenced listing image files from the cache root directory."""
    from ebay_workflows.services.image_cache_prune import prune_unreferenced_listing_images

    settings = load_settings(action="prune image cache")
    with cli_session(action="prune image cache", settings=settings) as (_, session):
        report = prune_unreferenced_listing_images(
            session,
            settings.image_cache_dir,
            dry_run=dry_run,
        )

    mode = "would remove" if report.dry_run else "removed"
    mb = report.bytes_reclaimed / (1024 * 1024)
    console.print(
        f"[bold green]Image cache prune complete.[/bold green] "
        f"Referenced: [cyan]{report.referenced_files}[/cyan]; "
        f"{mode}: [cyan]{report.orphan_files}[/cyan] file(s) "
        f"([cyan]{mb:.2f}[/cyan] MB) under [cyan]{report.cache_dir}[/cyan]"
    )

