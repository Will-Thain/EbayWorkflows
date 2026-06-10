from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.config import Settings
from ebay_workflows.models import Base
from ebay_workflows.operations.health_checks import collect_operational_health


def test_collect_operational_health_reports_missing_bulk_file(tmp_path) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    settings = Settings(
        DATABASE_URL="postgresql://postgres:postgres@localhost:5432/ebay_workflows",
        SCRYFALL_BULK_URI="https://api.scryfall.com/bulk-data/default-cards",
        CARDMARKET_BULK_FILE_PATH=str(tmp_path / "missing.csv"),
        IMAGE_CACHE_DIR=str(tmp_path / "images"),
        FAISS_INDEX_PATH=str(tmp_path / "missing.faiss"),
        GLOBAL_REQUESTS_PER_MINUTE_CAP="90",
        ENABLE_EBAY_API="false",
        DISABLE_LIVE_API_WRITES="true",
    )
    health = collect_operational_health(session, settings)
    assert health["faiss_index_ready"] is False
    assert health["cardmarket_bulk_missing"] is True
