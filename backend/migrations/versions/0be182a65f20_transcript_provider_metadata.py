"""transcript_provider_metadata

Revision ID: 0be182a65f20
Revises: 0bcdd7ad9c4a
Create Date: 2026-11-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0be182a65f20"
down_revision: Union[str, Sequence[str], None] = "0bcdd7ad9c4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transcripts", sa.Column("provider", sa.String(length=32), nullable=True))
    op.add_column("transcripts", sa.Column("model", sa.String(length=128), nullable=True))
    op.add_column("transcripts", sa.Column("detected_language", sa.String(length=32), nullable=True))
    op.add_column(
        "transcripts",
        sa.Column("transcribed_duration_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transcripts", "transcribed_duration_seconds")
    op.drop_column("transcripts", "detected_language")
    op.drop_column("transcripts", "model")
    op.drop_column("transcripts", "provider")
