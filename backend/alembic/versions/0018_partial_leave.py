"""partial-day leave (hourly permission) — 2026-09-19.

A leave record with start_time/end_time set covers only that window on a single
date — the employee still works the rest of the shift, and the permission
excuses lateness/early-departure/break penalties that fall inside the window
(client req 4, 6, 14). Both times NULL keeps the existing full-day behaviour.

Revision ID: 0018_partial_leave
Revises: 0017_occurrence_penalty
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_partial_leave"
down_revision = "0017_occurrence_penalty"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leave_records", sa.Column("start_time", sa.Time(), nullable=True))
    op.add_column("leave_records", sa.Column("end_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("leave_records", "end_time")
    op.drop_column("leave_records", "start_time")
