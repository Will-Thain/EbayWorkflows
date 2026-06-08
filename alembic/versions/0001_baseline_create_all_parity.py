"""Baseline revision (draft).

Existing databases were created with ``ebay-workflows init-db`` (``Base.metadata.create_all``).
This revision is intentionally empty: stamp existing DBs with ``alembic stamp head`` before
applying future autogenerate revisions. Do not run ``alembic upgrade head`` on production
until incremental migrations replace create_all for schema changes.
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
