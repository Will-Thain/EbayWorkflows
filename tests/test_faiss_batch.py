from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from ebay_workflows.models import Base, ScryfallCard
from ebay_workflows.services.embedding_index import _select_cards_for_batch


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_select_cards_for_batch_excludes_indexed() -> None:
    session = _session()
    id_a = uuid.uuid4()
    id_b = uuid.uuid4()
    id_c = uuid.uuid4()
    session.add_all(
        [
            ScryfallCard(id=id_a, name="A", image_normal="http://a", raw_payload_json={}),
            ScryfallCard(id=id_b, name="B", image_normal="http://b", raw_payload_json={}),
            ScryfallCard(id=id_c, name="C", image_normal="http://c", raw_payload_json={}),
        ]
    )
    session.commit()

    first = _select_cards_for_batch(session, batch_size=2, exclude_ids=set())
    assert len(first) == 2
    first_ids = {str(card.id) for card in first}
    assert first_ids.issubset({str(id_a), str(id_b), str(id_c)})

    second = _select_cards_for_batch(
        session,
        batch_size=2,
        exclude_ids=first_ids,
    )
    assert len(second) == 1
    assert str(second[0].id) not in first_ids
