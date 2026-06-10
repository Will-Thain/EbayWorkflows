"""One-off import fixes after ADR 0002 package move."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "ebay_workflows"

REPLACEMENTS: list[tuple[str, str]] = [
    # recognition internal
    ("from ..recognition.catalog_index", "from .catalog_index"),
    ("from ..recognition.region_crop_match", "from .region_crop_match"),
    ("from ..recognition.title_match", "from .title_match"),
    ("from ..recognition.set_symbol_templates", "from .set_symbol_templates"),
    ("from .progress_report", "from ..operations.progress_report"),
    ("from .match_event_log", "from ..operations.match_event_log"),
    # scoring
    ("from .image_evidence", "from ..candidates.image_evidence"),
    ("from .listing_filters", "from ..services.listing_filters"),
    # operations
    ("from .embedding_index", "from ..recognition.embedding_index"),
    ("from .set_symbol_match", "from ..recognition.set_symbol_match"),
    ("from ..gui.workflow_catalog", "from ..workflows.catalog"),
    # workflows package (was repo root)
    ("from .config", "from ..config"),
    ("from .models", "from ..models"),
    ("from .workflow_errors", "from ..workflow_errors"),
    ("from .integrations.", "from ..integrations."),
    ("from .recognition.", "from ..recognition."),
    ("from .services.candidate_attach", "from ..candidates.candidate_attach"),
    ("from .services.candidate_sync", "from ..candidates.candidate_sync"),
    ("from .services.candidate_gate", "from ..candidates.candidate_gate"),
    ("from .services.candidate_selection", "from ..candidates.candidate_selection"),
    ("from .services.image_evidence", "from ..candidates.image_evidence"),
    ("from .services.image_analysis", "from ..recognition.phase5_analysis"),
    ("from .services.embedding_index", "from ..recognition.embedding_index"),
    ("from .services.set_symbol_match", "from ..recognition.set_symbol_match"),
    ("from .services.lot_crop_match", "from ..recognition.lot_crop_match"),
    ("from .services.card_zones", "from ..recognition.card_zones"),
    ("from .services.currency", "from ..scoring.currency"),
    ("from .services.ev_guardrails", "from ..scoring.ev_guardrails"),
    ("from .services.hybrid_scoring", "from ..scoring.hybrid_scoring"),
    ("from .services.listing_condition", "from ..scoring.listing_condition"),
    ("from .services.image_cache", "from ..operations.image_cache"),
    ("from .services.image_cache_prune", "from ..operations.image_cache_prune"),
    ("from .services.pipeline_lock", "from ..operations.pipeline_lock"),
    ("from .services.progress_report", "from ..operations.progress_report"),
    ("from .services.workflow_progress", "from ..operations.workflow_progress"),
    ("from .services.match_event_log", "from ..operations.match_event_log"),
    ("from .services.match_stats", "from ..operations.match_stats"),
    ("from .services.ranked_export", "from ..operations.ranked_export"),
    ("from .services.health_checks", "from ..operations.health_checks"),
    ("from .services.db_indexes", "from ..operations.db_indexes"),
    ("from .services.detached_jobs", "from ..operations.detached_jobs"),
    ("from .services.ingest_helpers", "from ..operations.ingest_helpers"),
    ("from .services.rate_limit", "from ..operations.rate_limit"),
    ("from .services.clear_matching_data", "from ..operations.clear_matching_data"),
    ("from .services.stale_workflows", "from ..operations.stale_workflows"),
    ("from .services.workflow_logs", "from ..operations.workflow_logs"),
    ("from .services.listing_filters", "from ..services.listing_filters"),
    ("from .services.workflow_sample", "from ..services.workflow_sample"),
    ("from .services.bulk_lot_detection", "from ..services.bulk_lot_detection"),
    # gui / root still pointing at services
    ("from ..services.progress_report", "from ..operations.progress_report"),
    ("from ..services.workflow_progress", "from ..operations.workflow_progress"),
    ("from ..services.stale_workflows", "from ..operations.stale_workflows"),
    ("from ..services.ranked_export", "from ..operations.ranked_export"),
    ("from ..services.match_stats", "from ..operations.match_stats"),
    ("from ..services.workflow_logs", "from ..operations.workflow_logs"),
    ("from ..services.rate_limit", "from ..operations.rate_limit"),
    ("from ..services.ingest_helpers", "from ..operations.ingest_helpers"),
    ("from .services.workflow_sample", "from ..services.workflow_sample"),
    ("from .services.detached_jobs", "from ..operations.detached_jobs"),
    # integrations
    ("from ..services.rate_limit", "from ..operations.rate_limit"),
    ("from ..services.ingest_helpers", "from ..operations.ingest_helpers"),
]

WORKFLOW_FILES = list((ROOT / "workflows").glob("phase*.py"))

def patch_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for old, new in REPLACEMENTS:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = 0
    for path in ROOT.rglob("*.py"):
        if path.name == "fix_migration_imports.py":
            continue
        if patch_file(path):
            changed += 1
            print(f"patched {path.relative_to(ROOT.parent.parent)}")
    print(f"done: {changed} files")


if __name__ == "__main__":
    main()
