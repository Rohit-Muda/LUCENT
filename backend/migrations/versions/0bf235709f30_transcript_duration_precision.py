"""transcript_duration_precision

Revision ID: 0bf235709f30
Revises: 0be182a65f20
Create Date: 2026-11-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0bf235709f30"
down_revision: Union[str, Sequence[str], None] = "0be182a65f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "transcripts",
        "transcribed_duration_seconds",
        existing_type=sa.Float(),
        type_=sa.Double(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "transcripts",
        "transcribed_duration_seconds",
        existing_type=sa.Double(),
        type_=sa.Float(),
        existing_nullable=True,
    )
