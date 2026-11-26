"""processing_job_leases

Revision ID: 0bcdd7ad9c4a
Revises: 80f9746518c5
Create Date: 2026-11-27

"""
from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "0bcdd7ad9c4a"
down_revision: Union[str, Sequence[str], None] = "80f9746518c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("available_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("processing_jobs", sa.Column("attempts_by_stage", sa.JSON(), nullable=True))
    op.add_column(
        "processing_jobs",
        sa.Column("manual_retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.execute(
        sa.text(
            "UPDATE processing_jobs SET attempts_by_stage = JSON_OBJECT() "
            "WHERE attempts_by_stage IS NULL"
        )
    )
    op.alter_column("processing_jobs", "attempts_by_stage", existing_type=sa.JSON(), nullable=False)
    op.alter_column(
        "processing_jobs",
        "manual_retry_count",
        existing_type=sa.Integer(),
        server_default=None,
    )
    op.create_index(
        "ix_processing_jobs_status_available_at",
        "processing_jobs",
        ["status", "available_at"],
        unique=False,
    )

    bind = op.get_bind()
    legacy_lecture_ids = bind.execute(
        sa.text(
            "SELECT lectures.id FROM lectures "
            "LEFT JOIN processing_jobs ON processing_jobs.lecture_id = lectures.id "
            "WHERE processing_jobs.id IS NULL AND lectures.status = 'uploaded'"
        )
    ).scalars().all()
    if legacy_lecture_ids:
        op.bulk_insert(
            sa.table(
                "processing_jobs",
                sa.column("id", sa.String(36)),
                sa.column("lecture_id", sa.String(36)),
                sa.column("status", sa.String(32)),
                sa.column("current_stage", sa.String(64)),
                sa.column("retry_count", sa.Integer()),
                sa.column("attempts_by_stage", sa.JSON()),
                sa.column("manual_retry_count", sa.Integer()),
            ),
            [
                {
                    "id": str(uuid4()),
                    "lecture_id": lecture_id,
                    "status": "queued",
                    "current_stage": "validate_upload",
                    "retry_count": 0,
                    "attempts_by_stage": {},
                    "manual_retry_count": 0,
                }
                for lecture_id in legacy_lecture_ids
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_status_available_at", table_name="processing_jobs")
    op.drop_column("processing_jobs", "manual_retry_count")
    op.drop_column("processing_jobs", "attempts_by_stage")
    op.drop_column("processing_jobs", "available_at")
