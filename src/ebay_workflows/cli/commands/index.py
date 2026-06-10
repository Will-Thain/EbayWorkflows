from __future__ import annotations

import typer
from rich.table import Table

from ebay_workflows.cli.bootstrap import app, console
from ebay_workflows.cli_context import cli_session, load_settings

from ebay_workflows.recognition.embedding_index import (
    append_faiss_batch,
    build_faiss_index,
    build_faiss_index_all_batches,
    count_indexable_art_cards,
    indexed_scryfall_ids,
)
from ebay_workflows.recognition.set_symbol_match import build_set_symbol_templates, set_symbol_template_dir

@app.command("build-set-symbol-templates")
def build_set_symbol_templates_cmd() -> None:
    """Build set-symbol template images from Scryfall reference art (one per set)."""
    with cli_session(action="build set symbol templates") as (settings, session):
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
    settings = load_settings(action="build FAISS index")
    limit = max_cards if max_cards is not None else settings.faiss_build_max_cards
    with cli_session(action="build FAISS index", settings=settings) as (_, session):
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
    settings = load_settings(action="build FAISS batches")
    batch = batch_size if batch_size is not None else settings.faiss_build_max_cards
    with cli_session(action="build FAISS batches", settings=settings) as (_, session):
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


