"""split shifts + overtime pre-approval — 2026-09-17.

Two independent changes that both landed with the multi-shift request:

1. `shift_work_windows`: a weekday can now carry SEVERAL work blocks
   (08:00-12:00 + 17:00-21:00), not just one. Existing
   `shift_schedule_days.work_start_time/work_end_time` are kept, but from
   here on they are a DERIVED cache of the day's outer bounds (earliest
   window start, latest window end), maintained by the single write path
   `PUT /shift-schedules/{id}/days`. Consumers that only need the day's span
   (the "not checked in" alert, daily-status display) keep working
   untouched; anything doing per-window math reads the new table.

2. `attendance_daily_status.overtime_approved_at/by`: wires up the
   long-dormant `overtime_config.requires_preapproval` flag. When that flag
   is on, a day's overtime minutes are recorded but pay nothing until
   someone with access approves that specific day.

Revision ID: 0011_split_shifts_ot_approval
Revises: 0010_hikvision_cloud_device_type
Create Date: 2026-09-17

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0011_split_shifts_ot_approval"
down_revision = "0010_hikvision_cloud_device_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shift_work_windows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "shift_schedule_day_id",
            sa.Integer(),
            sa.ForeignKey("shift_schedule_days.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("work_start_time", sa.Time(), nullable=False),
        sa.Column("work_end_time", sa.Time(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_shift_work_windows_day", "shift_work_windows", ["shift_schedule_day_id", "sort_order"]
    )

    # Backfill: every working day that already has a start AND end becomes a
    # single window, so nothing about existing schedules changes behaviour.
    # Days missing either time are left window-less — recompute treats that
    # exactly as it treats a day with no times today (no late/early math).
    op.execute(
        """
        INSERT INTO shift_work_windows (shift_schedule_day_id, work_start_time, work_end_time, sort_order)
        SELECT id, work_start_time, work_end_time, 0
        FROM shift_schedule_days
        WHERE is_working_day IS TRUE
          AND work_start_time IS NOT NULL
          AND work_end_time IS NOT NULL
        """
    )

    op.add_column(
        "attendance_daily_status",
        sa.Column("overtime_approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "attendance_daily_status",
        sa.Column(
            "overtime_approved_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Collapse each day's windows back into the single start/end pair the old
    # schema could express (outer bounds), so a downgraded schedule still
    # covers the same span of the day rather than losing the later blocks.
    op.execute(
        """
        UPDATE shift_schedule_days d
        SET work_start_time = w.min_start,
            work_end_time = w.max_end
        FROM (
            SELECT shift_schedule_day_id,
                   MIN(work_start_time) AS min_start,
                   MAX(work_end_time) AS max_end
            FROM shift_work_windows
            GROUP BY shift_schedule_day_id
        ) w
        WHERE d.id = w.shift_schedule_day_id
        """
    )
    op.drop_column("attendance_daily_status", "overtime_approved_by_user_id")
    op.drop_column("attendance_daily_status", "overtime_approved_at")
    op.drop_index("ix_shift_work_windows_day", table_name="shift_work_windows")
    op.drop_table("shift_work_windows")
