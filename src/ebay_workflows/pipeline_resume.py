from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .integrations.scryfall import sync_scryfall_bulk
from .models import CardPrice, ImageDetection, Listing, ListingCardCandidate, ListingScore, OcrResult, ScryfallCard, WorkflowStep
from .workflow_phase1 import run_phase1
from .workflow_phase2 import run_phase2_title_match, upsert_scryfall_cards
from .workflow_phase3 import run_phase3_join, sync_cardmarket_prices
from .workflow_phase4 import run_phase4_ranking
from .workflow_phase5 import run_phase5_ocr_verification
from .workflow_phase6 import run_phase6_bulk_lot_detection
from .services.workflow_sample import with_sample_overrides


@dataclass(slots=True)
class ResumablePipelineConfig:
    query: str
    max_pages: int
    mock_input_file: str | None
    download_images: bool
    top_k: int
    mock_ocr_file: str | None
    use_real_ocr: bool
    mock_lot_file: str | None
    use_real_lot_detection: bool
    from_phase: int
    to_phase: int
    resume: bool
    workflow_max_listings: int | None = None
    workflow_max_images: int | None = None
    workflow_singles_only: bool = False


def _count(session: Session, model: Any) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar_one())


def _phase_completion_snapshot(
    session: Session,
    *,
    max_pages: int = 1,
    page_size: int = 50,
) -> dict[int, bool]:
    listings_count = _count(session, Listing)
    candidates_count = _count(session, ListingCardCandidate)
    prices_count = _count(session, CardPrice)
    scores_count = _count(session, ListingScore)
    card_region_count = int(
        session.execute(
            select(func.count()).select_from(ImageDetection).where(ImageDetection.detection_type == "card_region")
        ).scalar_one()
    )
    lot_card_count = int(
        session.execute(
            select(func.count()).select_from(ImageDetection).where(ImageDetection.detection_type == "lot_card")
        ).scalar_one()
    )
    ocr_count = int(
        session.execute(select(func.count()).select_from(OcrResult).where(OcrResult.field_type == "title")).scalar_one()
    )
    lot_scores = int(
        session.execute(
            select(func.count()).select_from(ListingScore).where(ListingScore.scoring_version == "v2_lot")
        ).scalar_one()
    )

    phase1_complete = False
    if listings_count > 0:
        last_phase1 = session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.step_name == "phase1_ingest", WorkflowStep.status == "succeeded")
            .order_by(WorkflowStep.finished_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last_phase1 and last_phase1.metrics_json:
            seen = int(last_phase1.metrics_json.get("records_seen", 0))
            expected_floor = max(1, int(max_pages * page_size * 0.25))
            phase1_complete = seen >= expected_floor

    return {
        1: phase1_complete,
        2: candidates_count > 0,
        3: prices_count > 0 and candidates_count > 0,
        4: scores_count > 0,
        5: card_region_count > 0 and ocr_count > 0,
        6: lot_card_count > 0 and lot_scores > 0,
    }


def run_resumable_pipeline(
    session: Session,
    settings: Settings,
    cfg: ResumablePipelineConfig,
) -> dict[str, Any]:
    if cfg.from_phase < 1 or cfg.to_phase > 6 or cfg.from_phase > cfg.to_phase:
        raise ValueError("Phase range must satisfy 1 <= from_phase <= to_phase <= 6.")

    settings = with_sample_overrides(
        settings,
        max_listings=cfg.workflow_max_listings,
        max_images=cfg.workflow_max_images,
        singles_only=cfg.workflow_singles_only if cfg.workflow_max_listings else None,
    )

    phase_done = _phase_completion_snapshot(
        session,
        max_pages=cfg.max_pages,
        page_size=settings.ebay_page_size,
    )
    summary: dict[str, Any] = {"executed": {}, "skipped": []}

    # Production order: price join (3) after image verification (5); rank (4) after lot detection (6).
    execution_order = (1, 2, 5, 3, 6, 4)

    for phase in execution_order:
        if phase < cfg.from_phase or phase > cfg.to_phase:
            continue
        if cfg.resume and phase_done.get(phase, False):
            summary["skipped"].append(phase)
            continue

        if phase == 1:
            run_id = run_phase1(
                session=session,
                settings=settings,
                query=cfg.query,
                max_pages=cfg.max_pages,
                mock_input_file=cfg.mock_input_file,
                download_images=cfg.download_images,
            )
        elif phase == 2:
            if _count(session, ScryfallCard) == 0:
                cards = sync_scryfall_bulk(settings)
                upsert_scryfall_cards(session, cards)
            run_id = run_phase2_title_match(session, settings=settings, top_k=cfg.top_k)
        elif phase == 3:
            if _count(session, CardPrice) == 0:
                sync_cardmarket_prices(session, settings)
            run_id = run_phase3_join(session, settings)
        elif phase == 4:
            run_id = run_phase4_ranking(session, settings)
        elif phase == 5:
            if not cfg.mock_ocr_file and not cfg.use_real_ocr:
                raise ValueError("Phase 5 requires --mock-ocr-file or --use-real-ocr.")
            run_id = run_phase5_ocr_verification(
                session,
                settings,
                mock_ocr_file=cfg.mock_ocr_file,
                use_real_ocr=cfg.use_real_ocr,
            )
        else:
            if not cfg.mock_lot_file and not cfg.use_real_lot_detection:
                raise ValueError("Phase 6 requires --mock-lot-file or --use-real-lot-detection.")
            run_id = run_phase6_bulk_lot_detection(
                session,
                settings,
                mock_lot_file=cfg.mock_lot_file,
                use_real_detection=cfg.use_real_lot_detection,
            )

        summary["executed"][f"phase_{phase}"] = run_id

    return summary
