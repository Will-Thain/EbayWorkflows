from __future__ import annotations

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .config import Settings

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
) -> None:
    """Stub workflow command with policy-safe startup checks."""
    try:
        settings = Settings()
    except (ValidationError, ValueError) as exc:
        console.print(f"[bold red]Cannot start workflow:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    if not settings.enable_provider_policy_checks:
        console.print("[bold red]Policy checks must be enabled to run workflows.[/bold red]")
        raise typer.Exit(code=4)

    effective_dry_run = dry_run or settings.disable_live_api_writes
    console.print("[bold]Workflow startup checks passed.[/bold]")
    console.print(f"Query: [cyan]{query}[/cyan]")
    console.print(f"Dry run mode: [yellow]{effective_dry_run}[/yellow]")
    console.print("Next step: implement phase executors and DB persistence.")


if __name__ == "__main__":
    app()

