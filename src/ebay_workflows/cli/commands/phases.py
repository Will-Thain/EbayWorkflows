from __future__ import annotations

import typer
from rich.table import Table

from ebay_workflows.cli.bootstrap import app, console
from ebay_workflows.cli_context import cli_session, load_settings

from ebay_workflows.services.clear_matching_data import clear_matching_artifacts, count_matching_artifacts
from ebay_workflows.services.ingest_helpers import resolve_max_pages
from ebay_workflows.pipeline_resume import ResumablePipelineConfig, run_resumable_pipeline
from ebay_workflows.workflow_phase2 import load_cards_from_cache, run_phase2_title_match
from ebay_workflows.workflow_phase3 import run_phase3_join
from ebay_workflows.workflow_phase4 import run_phase4_ranking
from ebay_workflows.workflow_phase5 import run_phase5_ocr_verification
from ebay_workflows.workflow_phase6 import run_phase6_bulk_lot_detection

@app.command("phase2-match-title")
def phase2_match_title(
    top_k: int = typer.Option(3, "--top-k", help="Top candidate cards retained per listing"),
) -> None:
    """Run Milestone 2 title-based listing to Scryfall matching."""
    with cli_session(action="start Phase 2") as (settings, session):
        # Ensure local cache is present and structured before matching.
        load_cards_from_cache(settings)
        run_id = run_phase2_title_match(session, settings=settings, top_k=top_k)

    console.print("[bold green]Phase 2 title matching completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


@app.command("phase3-join-prices")
def phase3_join_prices() -> None:
    """Run Milestone 3 Cardmarket price join for matched candidates."""
    with cli_session(action="start Phase 3") as (settings, session):
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
    with cli_session(action="start Phase 4") as (settings, session):
        run_id = run_phase4_ranking(session, settings, use_hybrid=hybrid)
    console.print("[bold green]Phase 4 ranking completed.[/bold green]")
    console.print(f"Run ID: [cyan]{run_id}[/cyan]")


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
    with cli_session(action="start Phase 5") as (settings, session):
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
    with cli_session(action="start Phase 6") as (settings, session):
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
    settings = load_settings(action="clear match data")
    with cli_session(action="clear match data", settings=settings) as (_, session):
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

    with cli_session(action="clear match data", settings=settings) as (_, session):
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
    settings = load_settings(action="start resumable pipeline")

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

    with cli_session(action="start resumable pipeline", settings=settings) as (_, session):
        summary = run_resumable_pipeline(session, settings, cfg)

    table = Table(title="Resumable Pipeline Result")
    table.add_column("Type", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Executed", str(summary.get("executed", {})))
    table.add_row("Skipped phases", str(summary.get("skipped", [])))
    console.print(table)

