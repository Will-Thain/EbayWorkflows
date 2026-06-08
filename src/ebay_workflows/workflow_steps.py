from __future__ import annotations

STEP_TO_JOB: dict[str, str] = {
    "phase1_ingest": "phase1",
    "phase2_title_match": "phase2",
    "phase3_cardmarket_join": "phase3",
    "phase4_ev_ranking": "phase4",
    "phase5_ocr_verification": "phase5",
    "phase6_bulk_lot_detection": "phase6",
}


def job_id_for_step(step_name: str) -> str:
    return STEP_TO_JOB.get(step_name, step_name)
