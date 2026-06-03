from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .config import Settings
from .integrations.cardmarket import load_cardmarket_bulk_rows
from .models import CardPrice, ListingCardCandidate, ScryfallCard, WorkflowRun, WorkflowStep


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def sync_cardmarket_prices(session: Session, settings: Settings) -> int:
    rows = load_cardmarket_bulk_rows(settings.cardmarket_bulk_file_path)
    cards = session.execute(select(ScryfallCard.id, ScryfallCard.name)).all()
    name_map = {name.lower(): card_id for card_id, name in cards}

    # Multiple Cardmarket products can share a name; keep the highest price per snapshot key.
    pending: dict[tuple[uuid.UUID, str, str | None, str | None, str], tuple[Decimal, dict[str, Any]]] = {}
    for row in rows:
        scryfall_id = _as_uuid((row.get("scryfall_id") or "").strip())
        if scryfall_id is None:
            name = (row.get("name") or "").strip().lower()
            scryfall_id = name_map.get(name)
        if scryfall_id is None:
            continue

        price_value = row.get("price_eur") or row.get("price_amount")
        if not price_value:
            continue
        price_amount = Decimal(str(price_value))
        condition = (row.get("condition") or "").strip() or None
        language = (row.get("language") or "").strip() or None
        price_type = (row.get("price_type") or "trend").strip() or "trend"
        price_timestamp = (row.get("price_timestamp") or _now().isoformat()).strip()

        key = (scryfall_id, price_type, condition, language, price_timestamp)
        existing = pending.get(key)
        if existing is None or price_amount > existing[0]:
            pending[key] = (price_amount, row)

    inserted = 0
    for (scryfall_id, price_type, condition, language, price_timestamp), (price_amount, row) in pending.items():
        session.execute(
            delete(CardPrice).where(
                CardPrice.source == "cardmarket",
                CardPrice.scryfall_id == scryfall_id,
                CardPrice.price_type == price_type,
                CardPrice.condition == condition,
                CardPrice.language == language,
                CardPrice.price_timestamp == price_timestamp,
            )
        )
        session.add(
            CardPrice(
                source="cardmarket",
                scryfall_id=scryfall_id,
                currency=(row.get("currency") or "EUR").strip() or "EUR",
                price_type=price_type,
                condition=condition,
                language=language,
                price_amount=price_amount,
                price_timestamp=price_timestamp,
                raw_payload_json=row,
            )
        )
        inserted += 1

    session.commit()
    return inserted


def run_phase3_join(session: Session, settings: Settings) -> str:
    run = WorkflowRun(
        workflow_name=f"{settings.workflow_default_name}_phase3",
        status="running",
        input_config_json={"source": "cardmarket_bulk_join"},
        started_at=_now(),
    )
    session.add(run)
    session.flush()

    step = WorkflowStep(
        run_id=run.id,
        step_name="phase3_cardmarket_join",
        phase_number=3,
        status="running",
        attempt=1,
        started_at=_now(),
    )
    session.add(step)
    session.flush()

    try:
        candidates = session.execute(select(ListingCardCandidate)).scalars().all()
        prices = session.execute(select(CardPrice)).scalars().all()
        latest_by_card: dict[uuid.UUID, CardPrice] = {}
        latest_by_name: dict[str, CardPrice] = {}
        for price in prices:
            current = latest_by_card.get(price.scryfall_id)
            if current is None or price.price_timestamp > current.price_timestamp:
                latest_by_card[price.scryfall_id] = price
            if price.scryfall_card and price.scryfall_card.name:
                key = price.scryfall_card.name.lower()
                current_name = latest_by_name.get(key)
                if current_name is None or price.price_timestamp > current_name.price_timestamp:
                    latest_by_name[key] = price

        joined = 0
        for candidate in candidates:
            price = latest_by_card.get(candidate.scryfall_id) if candidate.scryfall_id else None
            if not price and candidate.scryfall_card and candidate.scryfall_card.name:
                price = latest_by_name.get(candidate.scryfall_card.name.lower())
            if not price:
                continue
            evidence: dict[str, Any] = dict(candidate.evidence_json or {})
            evidence["cardmarket_price"] = {
                "currency": price.currency,
                "price_amount": float(price.price_amount),
                "price_type": price.price_type,
                "price_timestamp": price.price_timestamp,
                "condition": price.condition,
                "language": price.language,
            }
            candidate.evidence_json = evidence
            joined += 1

        step.status = "succeeded"
        step.finished_at = _now()
        step.metrics_json = {
            "candidates_seen": len(candidates),
            "prices_available": len(prices),
            "candidates_joined": joined,
        }
        run.status = "succeeded"
        run.finished_at = _now()
        session.commit()
    except Exception as exc:  # noqa: BLE001
        step.status = "failed"
        step.finished_at = _now()
        step.error_json = {"message": str(exc)}
        run.status = "failed"
        run.finished_at = _now()
        session.commit()
        raise

    return str(run.id)

