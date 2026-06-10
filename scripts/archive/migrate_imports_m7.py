"""Bulk-update imports for ADR 0002 M7 (remove services/ shims)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS: list[tuple[str, str]] = [
    ("ebay_workflows.operations.clear_matching_data", "ebay_workflows.operations.clear_matching_data"),
    ("ebay_workflows.operations.ingest_helpers", "ebay_workflows.operations.ingest_helpers"),
    ("ebay_workflows.operations.workflow_sample", "ebay_workflows.operations.workflow_sample"),
    ("ebay_workflows.recognition.embedding_index", "ebay_workflows.recognition.embedding_index"),
    ("ebay_workflows.recognition.set_symbol_match", "ebay_workflows.recognition.set_symbol_match"),
    ("ebay_workflows.recognition.phase5_analysis", "ebay_workflows.recognition.phase5_analysis"),
    ("ebay_workflows.recognition.card_zones", "ebay_workflows.recognition.card_zones"),
    ("ebay_workflows.recognition.lot_crop_match", "ebay_workflows.recognition.lot_crop_match"),
    ("ebay_workflows.candidates.candidate_sync", "ebay_workflows.candidates.candidate_sync"),
    ("ebay_workflows.candidates.candidate_gate", "ebay_workflows.candidates.candidate_gate"),
    ("ebay_workflows.candidates.candidate_attach", "ebay_workflows.candidates.candidate_attach"),
    ("ebay_workflows.candidates.candidate_selection", "ebay_workflows.candidates.candidate_selection"),
    ("ebay_workflows.candidates.image_evidence", "ebay_workflows.candidates.image_evidence"),
    ("ebay_workflows.scoring.ev_guardrails", "ebay_workflows.scoring.ev_guardrails"),
    ("ebay_workflows.operations.listing_filters", "ebay_workflows.operations.listing_filters"),
    ("ebay_workflows.scoring.hybrid_scoring", "ebay_workflows.scoring.hybrid_scoring"),
    ("ebay_workflows.scoring.currency", "ebay_workflows.scoring.currency"),
    ("ebay_workflows.scoring.listing_condition", "ebay_workflows.scoring.listing_condition"),
    ("ebay_workflows.operations.ranked_export", "ebay_workflows.operations.ranked_export"),
    ("ebay_workflows.operations.match_stats", "ebay_workflows.operations.match_stats"),
    ("ebay_workflows.operations.pipeline_progress", "ebay_workflows.operations.pipeline_progress"),
    ("ebay_workflows.operations.stale_workflows", "ebay_workflows.operations.stale_workflows"),
    ("ebay_workflows.operations.workflow_logs", "ebay_workflows.operations.workflow_logs"),
    ("ebay_workflows.operations.detached_jobs", "ebay_workflows.operations.detached_jobs"),
    ("ebay_workflows.operations.db_indexes", "ebay_workflows.operations.db_indexes"),
    ("ebay_workflows.operations.health_checks", "ebay_workflows.operations.health_checks"),
    ("ebay_workflows.operations.image_cache", "ebay_workflows.operations.image_cache"),
    ("ebay_workflows.operations.image_cache_prune", "ebay_workflows.operations.image_cache_prune"),
    ("ebay_workflows.operations.progress_report", "ebay_workflows.operations.progress_report"),
    ("ebay_workflows.operations.workflow_progress", "ebay_workflows.operations.workflow_progress"),
    ("ebay_workflows.operations.match_event_log", "ebay_workflows.operations.match_event_log"),
    ("ebay_workflows.operations.pipeline_lock", "ebay_workflows.operations.pipeline_lock"),
    ("ebay_workflows.operations.rate_limit", "ebay_workflows.operations.rate_limit"),
    ("ebay_workflows.recognition.listing_lot_detection", "ebay_workflows.recognition.listing_lot_detection"),
    ("ebay_workflows.workflows.phase1", "ebay_workflows.workflows.phase1"),
    ("ebay_workflows.workflows.phase2", "ebay_workflows.workflows.phase2"),
    ("ebay_workflows.workflows.phase3", "ebay_workflows.workflows.phase3"),
    ("ebay_workflows.workflows.phase4", "ebay_workflows.workflows.phase4"),
    ("ebay_workflows.workflows.phase5", "ebay_workflows.workflows.phase5"),
    ("ebay_workflows.workflows.phase6", "ebay_workflows.workflows.phase6"),
]


def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8-sig")
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = 0
    for pattern in ("src/**/*.py", "tests/**/*.py", "scripts/**/*.py", "docs/**/*.md"):
        for path in ROOT.glob(pattern):
            if "services" in path.parts and path.parent.name == "services":
                continue
            if patch_file(path):
                changed += 1
                print(path.relative_to(ROOT))
    print(f"patched {changed} files")


if __name__ == "__main__":
    main()
