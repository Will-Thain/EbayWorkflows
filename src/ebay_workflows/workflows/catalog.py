from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class WorkflowJobDef:
    job_id: str
    label: str
    duration_tier: str  # short | medium | long
    build_argv: Callable[[dict[str, Any]], list[str]]


def _phase1_argv(params: dict[str, Any]) -> list[str]:
    argv = [
        "run",
        "--query",
        str(params.get("query", "magic the gathering")),
        "--no-dry-run",
        "--max-pages",
        str(int(params.get("max_pages", 1))),
    ]
    if params.get("download_images", True):
        argv.append("--download-images")
    else:
        argv.append("--no-download-images")
    return argv


def _simple_phase(phase_cmd: str) -> Callable[[dict[str, Any]], list[str]]:
    def _builder(params: dict[str, Any]) -> list[str]:
        if phase_cmd == "phase2-match-title":
            return [phase_cmd, "--top-k", str(int(params.get("top_k", 3)))]
        if phase_cmd == "phase4-rank" and params.get("hybrid", True):
            return [phase_cmd, "--hybrid"]
        return [phase_cmd]

    return _builder


def _pipeline_argv(params: dict[str, Any]) -> list[str]:
    argv = [
        "run-resumable-pipeline",
        "--query",
        str(params.get("query", "magic the gathering")),
        "--max-pages",
        str(int(params.get("max_pages", 1))),
        "--download-images",
        "--use-real-ocr",
        "--use-embedding-match",
        "--use-real-lot-detection",
    ]
    max_listings = params.get("max_listings")
    if max_listings:
        argv.extend(["--max-listings", str(int(max_listings))])
    return argv


WORKFLOW_JOBS: dict[str, WorkflowJobDef] = {
    "phase1": WorkflowJobDef("phase1", "Ingest eBay listings", "long", _phase1_argv),
    "phase2": WorkflowJobDef("phase2", "Title match", "long", _simple_phase("phase2-match-title")),
    "phase3": WorkflowJobDef("phase3", "Join Cardmarket prices", "short", _simple_phase("phase3-join-prices")),
    "sync_cm": WorkflowJobDef("sync_cm", "Sync Cardmarket bulk", "medium", _simple_phase("sync-cardmarket")),
    "phase4": WorkflowJobDef("phase4", "Rank (hybrid)", "medium", _simple_phase("phase4-rank")),
    "phase5": WorkflowJobDef(
        "phase5",
        "Image cascade (OCR + embeddings)",
        "long",
        lambda _p: ["phase5-verify-ocr", "--use-real-ocr", "--use-embedding-match"],
    ),
    "phase6": WorkflowJobDef(
        "phase6",
        "Bulk lot detection",
        "long",
        lambda _p: ["phase6-detect-lots", "--use-real-lot-detection"],
    ),
    "pipeline": WorkflowJobDef(
        "pipeline",
        "Resumable pipeline (2→5→3→6→4)",
        "long",
        _pipeline_argv,
    ),
    "integrity": WorkflowJobDef(
        "integrity", "Data integrity check", "short", _simple_phase("data-integrity-check")
    ),
    "export": WorkflowJobDef(
        "export",
        "Export rankings (JSON)",
        "short",
        lambda p: [
            "export-rankings",
            "--limit",
            str(int(p.get("limit", 50))),
            "-o",
            str(p.get("output", "./data/exports/ranked.json")),
        ],
    ),
}

# Display order on Workflows → Run now (pipeline flow, then utilities).
WORKFLOW_LAUNCH_ORDER: tuple[str, ...] = (
    "phase1",
    "pipeline",
    "phase2",
    "phase5",
    "phase3",
    "phase6",
    "phase4",
    "sync_cm",
    "integrity",
    "export",
)

LONG_RUNNING_SCHEDULE_JOBS = frozenset({"phase5", "phase6", "pipeline"})


def build_argv(job_id: str, params: dict[str, Any] | None = None) -> list[str]:
    job = WORKFLOW_JOBS.get(job_id)
    if not job:
        raise ValueError(f"Unknown job_id: {job_id}")
    return ["ebay-workflows", *job.build_argv(params or {})]
