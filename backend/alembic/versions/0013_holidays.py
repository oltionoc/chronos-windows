"""public holiday calendar — 2026-09-17.

`attendance_daily_status.status` has allowed 'holiday' since 0001 and
`overtime_config.holiday_rate_per_hour_eur` has existed just as long, but
nothing could ever set either: there was no source of truth for which dates
are holidays (flagged as a gap in services/payroll_calc.py's docstring).
Without it every public holiday either deducts an absence from someone who
was correctly off, or pays holiday work at the ordinary rate.

`location_id` NULL means "every location", the same convention the
penalty/overtime/absence config tables already use. `recurs_annually` covers
fixed-date holidays (1 January) without re-entering them every year;
moving ones (Eid, Easter) are entered per year with it off.

Revision ID: 0013_holidays
Revises: 0012_device_clock_skew
Create Date: 2026-09-17

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_holidays"
down_revision = "0012_device_clock_skew"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "holidays",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name_en", sa.Text(), nullable=False),
        sa.Column("name_sq", sa.Text(), nullable=False),
        sa.Column("recurs_annually", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_holidays_date", "holidays", ["holiday_date"])
    # One entry per date per scope. Two rows for the same day would make
    # "which name does this day have" ambiguous, and the recompute path has to
    # be able to answer that. Two partial indexes rather than one over
    # (location_id, holiday_date): in SQL, NULLs are distinct from each other,
    # so a plain unique index would happily allow ten org-wide rows on the
    # same date.
    op.create_index(
        "uq_holidays_location_date",
        "holidays",
        ["location_id", "holiday_date"],
        unique=True,
        postgresql_where=sa.text("location_id IS NOT NULL"),
    )
    op.create_index(
        "uq_holidays_global_date",
        "holidays",
        ["holiday_date"],
        unique=True,
        postgresql_where=sa.text("location_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_holidays_global_date", table_name="holidays")
    op.drop_index("uq_holidays_location_date", table_name="holidays")
    op.drop_index("ix_holidays_date", table_name="holidays")
    op.drop_table("holidays")
