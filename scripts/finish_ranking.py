"""Finish pipeline: phase4 rank, export, integrity — without full CLI import chain."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Phase 4 does not need GPU; directml init during Settings() can hang on Windows.
os.environ["TORCH_DEVICE"] = "cpu"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ebay_workflows.cli_context import cli_session, load_settings  # noqa: E402
from ebay_workflows.hardening import run_data_integrity_checks  # noqa: E402
from ebay_workflows.operations.ranked_export import fetch_ranked_listings, write_ranked_json  # noqa: E402
from ebay_workflows.workflows.phase4 import run_phase4_ranking  # noqa: E402


def main() -> int:
    settings = load_settings(action="finish ranking")
    export_path = ROOT / "data" / "exports" / "ranked-reanalyze.json"
    export_path.parent.mkdir(parents=True, exist_ok=True)

    print("Running phase4-rank (hybrid)...", flush=True)
    with cli_session(action="phase4 rank", settings=settings) as (_, session):
        run_id = run_phase4_ranking(session, settings, use_hybrid=True)
    print(f"Phase 4 completed. Run ID: {run_id}", flush=True)

    print("Exporting rankings...", flush=True)
    with cli_session(action="export rankings", settings=settings) as (_, session):
        rows = fetch_ranked_listings(session, limit=10_000)
    if not rows:
        print("No ranked listings found.", flush=True)
        return 3
    out = write_ranked_json(rows, str(export_path))
    print(f"Exported {len(rows)} listings to {out}", flush=True)

    print("Running data integrity checks...", flush=True)
    with cli_session(action="integrity check", settings=settings) as (_, session):
        report = run_data_integrity_checks(session)
    if report.issues_found:
        print(f"Integrity issues ({report.issues_found}):", flush=True)
        for detail in report.details:
            print(f"  - {detail}", flush=True)
        return 6
    print(f"Integrity checks passed ({report.checks_run} checks).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
