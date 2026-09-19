"""per-date rota: shift templates + roster entries — 2026-09-19.

The weekly shift schedule (recurring day_of_week pattern) stays, but a client
whose staff rotate freely — morning one day, afternoon the next — needs a
shift assigned per DATE, not per weekday. This adds:

  * shift_template: a named, reusable shift (work window + optional break +
    grace), e.g. "Paradite 10-18".
  * roster_entry: employee + date -> shift_template (or NULL = day off).

Resolution (services/shift_lookup.resolve_day): a roster entry for the date
wins; with no entry, the weekly schedule is used exactly as before, so every
existing schedule and test is unaffected.

Revision ID: 0016_rota
Revises: 0015_license_key
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_rota"
down_revision = "0015_license_key"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shift_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("work_start_time", sa.Time(), nullable=False),
        sa.Column("work_end_time", sa.Time(), nullable=False),
        sa.Column("break_start_time", sa.Time(), nullable=True),
        sa.Column("break_end_time", sa.Time(), nullable=True),
        sa.Column("break_is_paid", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("grace_minutes_late", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "roster_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        # NULL template = an explicit day off for that date (overrides the
        # weekly schedule's working day).
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_template.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_roster_employee_date"),
    )
    op.create_index("ix_roster_entry_date", "roster_entry", ["work_date"])


def downgrade() -> None:
    op.drop_index("ix_roster_entry_date", table_name="roster_entry")
    op.drop_table("roster_entry")
    op.drop_table("shift_template")
