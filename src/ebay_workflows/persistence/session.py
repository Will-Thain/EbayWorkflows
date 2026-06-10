"""SQLAlchemy session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings


def build_engine(settings: Settings):
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_max,
        max_overflow=0,
        pool_pre_ping=True,
    )


def build_session_factory(settings: Settings) -> sessionmaker[Session]:
    engine = build_engine(settings)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
