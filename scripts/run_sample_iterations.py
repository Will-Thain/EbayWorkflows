"""Run N iterative Phase 5 sample validations on single-card listings."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from ebay_workflows.config import Settings
from ebay_workflows.db import build_session_factory
from ebay_workflows.models import ListingCardCandidate
from ebay_workflows.operations.workflow_sample import (
    count_eligible_single_listings_with_images,
    discover_single_listings_with_images,
)


def _load_used_listing_ids(log_path: Path) -> set[uuid.UUID]:
    used: set[uuid.UUID] = set()
    if not log_path.is_file():
        return used
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        listing_id = record.get("listing_id")
        if not listing_id:
            continue
        try:
            used.add(uuid.UUID(str(listing_id)))
        except ValueError:
            continue
    return used


def _load_expert_review_module():
    path = Path(__file__).resolve().parent / "expert_review_listing.py"
    spec = importlib.util.spec_from_file_location("expert_review_listing", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load expert review module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_fix_agreement_module():
    path = Path(__file__).resolve().parent / "expert_fix_agreement.py"
    spec = importlib.util.spec_from_file_location("expert_fix_agreement", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load fix agreement module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(slots=True)
class SampleRunResult:
    run_number: int
    listing_id: str
    title: str
    exit_code: int
    images_analyzed: int = 0
    regions: int = 0
    verified: int = 0
    gated: int = 0
    candidates_before: int = 0
    error: str | None = None
    stdout_tail: str = ""


def _parse_summary(stdout: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in stdout.splitlines():
        for key in (
            "images_analyzed",
            "regions",
            "detections_persisted",
            "candidates_updated",
            "embedding_updates",
            "verified",
            "gated",
        ):
            match = re.search(rf"\b{key}=(\d+)", line)
            if match:
                out[key] = int(match.group(1))
    return out


def _run_validate(python: Path, repo_root: Path, listing_id: str, max_images: int) -> SampleRunResult:
    cmd = [
        str(python),
        str(repo_root / "scripts" / "validate_phase5_listing.py"),
        listing_id,
        "--max-images",
        str(max_images),
        "--use-embedding",
    ]
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    summary = _parse_summary(proc.stdout or "")
    return SampleRunResult(
        run_number=0,
        listing_id=listing_id,
        title="",
        exit_code=proc.returncode,
        images_analyzed=summary.get("images_analyzed", 0),
        regions=summary.get("regions", 0),
        verified=summary.get("verified", 0),
        gated=summary.get("gated", 0),
        error=None if proc.returncode == 0 else (proc.stderr or proc.stdout or "unknown error")[:500],
        stdout_tail=combined[-800:],
    )


def _ensure_phase2_candidates(cli: Path, repo_root: Path, max_listings: int = 1) -> None:
    if not cli.is_file():
        return
    subprocess.run(
        [
            str(cli),
            "phase2-match-title",
            "--top-k",
            "3",
            "--max-listings",
            str(max_listings),
            "--singles-only",
        ],
        cwd=repo_root,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Iterative sample runs on single listings")
    parser.add_argument("--count", type=int, default=20, help="Number of sample runs")
    parser.add_argument("--max-images", type=int, default=2, help="Images per listing validation")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N eligible fresh singles")
    parser.add_argument(
        "--fresh-batch",
        action="store_true",
        default=True,
        help="Exclude listings already present in --output log (default: on)",
    )
    parser.add_argument(
        "--no-fresh-batch",
        dest="fresh_batch",
        action="store_false",
        help="Allow re-selecting listings from prior batches",
    )
    parser.add_argument(
        "--allow-repeats",
        action="store_true",
        default=False,
        help="Cycle listings when --count exceeds fresh pool",
    )
    parser.add_argument(
        "--no-allow-repeats",
        dest="allow_repeats",
        action="store_false",
        help="Stop when fresh singles exhausted (default)",
    )
    parser.add_argument("--prep-phase2", action="store_true", help="Run phase2 on singles sample first")
    parser.add_argument("--max-listings", type=int, default=20, help="Singles cap for phase2 prep")
    parser.add_argument(
        "--expert-review",
        action="store_true",
        default=True,
        help="Run 5-agent expert panel review after each sample (default: on)",
    )
    parser.add_argument(
        "--no-expert-review",
        dest="expert_review",
        action="store_false",
        help="Skip expert panel review",
    )
    parser.add_argument(
        "--expert-output",
        default="./data/exports/sample-runs-expert.jsonl",
        help="Expert panel JSONL log path",
    )
    parser.add_argument(
        "--output",
        default="./data/exports/sample-runs.jsonl",
        help="JSONL log path",
    )
    parser.add_argument(
        "--fixes-output",
        default="./data/exports/sample-runs-fixes.jsonl",
        help="Expert fix agreement JSONL log path",
    )
    parser.add_argument(
        "--fixes-state",
        default="./data/exports/sample-fixes-applied.json",
        help="Applied fix IDs state file",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    python = repo_root / ".venv" / "Scripts" / "python.exe"
    cli = repo_root / ".venv" / "Scripts" / "ebay-workflows.exe"
    if not python.is_file():
        python = Path(sys.executable)

    settings = Settings()
    session_factory = build_session_factory(settings)
    output_path = Path(args.output)
    exclude_ids: set[uuid.UUID] = set()
    if args.fresh_batch:
        exclude_ids = _load_used_listing_ids(output_path)
        if exclude_ids:
            print(f"=== Fresh batch: excluding {len(exclude_ids)} listing(s) from prior runs ===")

    with session_factory() as session:
        fresh_available = count_eligible_single_listings_with_images(
            session,
            exclude_listing_ids=exclude_ids,
        )
        pool = discover_single_listings_with_images(
            session,
            limit=args.count,
            offset=args.offset,
            exclude_listing_ids=exclude_ids,
        )

    if not pool and not args.allow_repeats:
        print(
            f"No fresh single listings available (need {args.count}, have {fresh_available}). "
            "Ingest more singles with cached images, or pass --no-fresh-batch / --allow-repeats "
            "to reuse listings.",
            file=sys.stderr,
        )
        return 2

    if not pool:
        with session_factory() as session:
            pool = discover_single_listings_with_images(
                session,
                limit=10000,
                offset=args.offset,
            )
        if not pool:
            print("No eligible single listings with cached images found.", file=sys.stderr)
            return 2

    if args.allow_repeats and len(pool) < args.count:
        listings = [pool[i % len(pool)] for i in range(args.count)]
        print(f"=== Pool={len(pool)} listings; cycling to {args.count} runs ===")
    else:
        listings = pool[: args.count]
        if len(listings) < args.count:
            print(
                f"=== Fresh pool={fresh_available}; running {len(listings)}/{args.count} requested ===",
                file=sys.stderr,
            )

    if not listings:
        print("No listings selected for sample runs.", file=sys.stderr)
        return 2

    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(
        f"=== Batch {batch_id}: {len(listings)} listing(s), "
        f"{fresh_available} fresh eligible in catalog ==="
    )

    if args.prep_phase2 and cli.is_file():
        print(f"=== Prep: phase2 on {args.max_listings} singles ===")
        prep = subprocess.run(
            [
                str(cli),
                "phase2-match-title",
                "--top-k",
                "3",
                "--max-listings",
                str(args.max_listings),
                "--singles-only",
            ],
            cwd=repo_root,
            text=True,
        )
        if prep.returncode != 0:
            print("Phase 2 prep failed", file=sys.stderr)
            return prep.returncode

    output_path = Path(args.output)
    expert_output_path = Path(args.expert_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    expert_output_path.parent.mkdir(parents=True, exist_ok=True)

    expert_module = _load_expert_review_module() if args.expert_review else None
    fix_module = _load_fix_agreement_module() if args.expert_review else None

    results: list[SampleRunResult] = []
    verified_total = 0
    errors = 0
    p0_total = 0
    p0_code_counts: dict[str, int] = {}
    consensus_counts: dict[str, int] = {}
    fixes_applied: list[str] = []

    fixes_log = Path(args.fixes_output)
    fixes_state = Path(args.fixes_state)

    for index, listing in enumerate(listings, start=1):
        with session_factory() as session:
            candidates_before = session.execute(
                select(ListingCardCandidate.id).where(ListingCardCandidate.listing_id == listing.id)
            ).all()

        if len(candidates_before) == 0 and cli.is_file():
            print("  (no candidates — running phase2 for singles batch)")
            _ensure_phase2_candidates(cli, repo_root, max_listings=args.max_listings)
            with session_factory() as session:
                candidates_before = session.execute(
                    select(ListingCardCandidate.id).where(
                        ListingCardCandidate.listing_id == listing.id
                    )
                ).all()

        print(f"\n=== Sample run {index}/{len(listings)} ===")
        print(f"Listing: {listing.id}")
        print(f"Title:   {listing.title[:72]}")

        result = _run_validate(python, repo_root, str(listing.id), args.max_images)
        result.run_number = index
        result.title = listing.title
        result.candidates_before = len(candidates_before)
        results.append(result)

        if result.exit_code != 0:
            errors += 1
            print(f"FAILED exit={result.exit_code}: {result.error}")
        else:
            verified_total += result.verified
            print(
                f"OK regions={result.regions} verified={result.verified} "
                f"gated={result.gated} candidates_before={result.candidates_before}"
            )

        record = asdict(result)
        record["ts"] = datetime.now(timezone.utc).isoformat()
        record["batch_id"] = batch_id
        with output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

        if expert_module is not None and result.exit_code == 0:
            run_metrics = {
                "regions": result.regions,
                "verified": result.verified,
                "gated": result.gated,
                "images_analyzed": result.images_analyzed,
            }
            with session_factory() as session:
                verdict = expert_module.review_listing(
                    session,
                    listing.id,
                    run_metrics=run_metrics,
                )
            expert_module.print_verdict(verdict)
            p0_total += len(verdict.p0_actions)
            consensus_counts[verdict.consensus] = consensus_counts.get(verdict.consensus, 0) + 1
            for comment in verdict.comments:
                if comment.priority == "P0" and comment.vote == "ACTION":
                    p0_code_counts[comment.code] = p0_code_counts.get(comment.code, 0) + 1
                # Legacy alias: repeated empty OCR parse drove false E1-BOTTOM P0 in prior batches
                if comment.code == "E1-BOTTOM-OCR":
                    p0_code_counts["E1-BOTTOM"] = p0_code_counts.get("E1-BOTTOM", 0) + 1
            expert_record = verdict.to_dict()
            expert_record["run_number"] = index
            expert_record["batch_id"] = batch_id
            expert_record["ts"] = datetime.now(timezone.utc).isoformat()
            if verdict.comments:
                with session_factory() as session:
                    ev_data = expert_module._collect_listing_evidence(session, listing.id)
                expert_record["bottom_parsed_key_count"] = ev_data.get("bottom_parsed_key_count", 0)
                expert_record["bottom_parsed_with_ids_count"] = ev_data.get(
                    "bottom_parsed_with_ids_count", 0
                )
            with expert_output_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(expert_record, default=str) + "\n")

            if fix_module is not None:
                agreements = fix_module.maybe_confer_and_apply(
                    p0_code_counts=p0_code_counts,
                    repo_root=repo_root,
                    fixes_log=fixes_log,
                    state_path=fixes_state,
                    run_number=index,
                )
                for agreement in agreements:
                    if agreement.approved:
                        fixes_applied.append(agreement.fix_id)
                        expert_module = _load_expert_review_module()

    print("\n=== Aggregate ===")
    print(f"runs={len(results)} errors={errors} total_verified={verified_total}")
    if expert_module is not None:
        print(f"expert_p0_actions={p0_total} consensus={consensus_counts}")
        print(f"p0_code_counts={p0_code_counts}")
        if fixes_applied:
            print(f"fixes_applied={fixes_applied} log={fixes_log.resolve()}")
        print(f"expert_log={expert_output_path.resolve()}")
    print(f"log={output_path.resolve()}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
