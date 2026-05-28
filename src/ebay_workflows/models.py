from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    input_config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["WorkflowStep"]] = relationship(back_populates="run", cascade="all,delete-orphan")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"
    __table_args__ = (UniqueConstraint("run_id", "step_name", "attempt", name="uq_run_step_attempt"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_runs.id"), nullable=False)
    step_name: Mapped[str] = mapped_column(String(120), nullable=False)
    phase_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt: Mapped[int] = mapped_column(nullable=False, default=1)
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    error_json: Mapped[dict | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[WorkflowRun] = relationship(back_populates="steps")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="ebay")
    external_listing_id: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    listing_url: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    price_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    shipping_amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    condition_text: Mapped[str | None] = mapped_column(String(120))
    raw_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    images: Mapped[list["ListingImage"]] = relationship(back_populates="listing", cascade="all,delete-orphan")
    card_candidates: Mapped[list["ListingCardCandidate"]] = relationship(
        back_populates="listing", cascade="all,delete-orphan"
    )


class ListingImage(Base):
    __tablename__ = "listing_images"
    __table_args__ = (UniqueConstraint("listing_id", "source_url", name="uq_listing_image_url"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    local_path: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(128))
    download_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_json: Mapped[dict | None] = mapped_column(JSON)

    listing: Mapped[Listing] = relationship(back_populates="images")


class ScryfallCard(Base):
    __tablename__ = "scryfall_cards"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    oracle_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    set_code: Mapped[str | None] = mapped_column(String(16))
    collector_number: Mapped[str | None] = mapped_column(String(32))
    lang: Mapped[str | None] = mapped_column(String(12))
    released_at: Mapped[str | None] = mapped_column(String(32))
    image_normal: Mapped[str | None] = mapped_column(Text)
    image_small: Mapped[str | None] = mapped_column(Text)
    raw_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class ListingCardCandidate(Base):
    __tablename__ = "listing_card_candidates"
    __table_args__ = (
        UniqueConstraint(
            "listing_id",
            "scryfall_id",
            "source_method",
            name="uq_listing_scryfall_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    listing_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("listings.id"), nullable=False)
    source_method: Mapped[str] = mapped_column(String(64), nullable=False, default="title_match")
    scryfall_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("scryfall_cards.id"))
    match_score: Mapped[float] = mapped_column(Numeric(7, 6), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Numeric(7, 6), nullable=False)
    rank_position: Mapped[int] = mapped_column(nullable=False, default=1)
    evidence_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

    listing: Mapped[Listing] = relationship(back_populates="card_candidates")
    scryfall_card: Mapped[ScryfallCard | None] = relationship()

