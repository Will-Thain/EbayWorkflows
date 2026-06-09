"""Add listings.description_text for item detail ingest."""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_listing_description"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE listings ADD COLUMN IF NOT EXISTS description_text TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE listings DROP COLUMN IF EXISTS description_text")
