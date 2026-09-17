"""explicit overtime punches — 2026-09-17.

Both supported vendors can label a punch as overtime: Hikvision's
attendanceStatus enum carries `overtimeIn`/`overtimeOut` (confirmed in the
DS-K1T804AMF's own AcsEvent/capabilities), and ZKTeco terminals emit punch
codes 4/5 for the same thing. Until now the Hikvision adapter folded both
into ordinary work punches and the codes were treated as unremarkable work
punches, so the device's own statement "this stretch was overtime" was
discarded and overtime was only ever inferred from the schedule.

Storing them distinctly means deliberately-clocked overtime is separable from
"stayed a bit past the end of the shift", which is what
services/recompute.py now relies on to exempt the former from the daily
overtime threshold (see BACKEND_NOTES.md).

Revision ID: 0014_overtime_punch_types
Revises: 0013_holidays
Create Date: 2026-09-17

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0014_overtime_punch_types"
down_revision = "0013_holidays"
branch_labels = None
depends_on = None

PUNCH_TYPES = (
    "'check_in_work','check_out_work','check_in_break','check_out_break',"
    "'check_in_overtime','check_out_overtime','unclassified'"
)
HINT_TYPES = (
    "'check_in_work','check_out_work','check_in_break','check_out_break',"
    "'check_in_overtime','check_out_overtime'"
)
OLD_PUNCH_TYPES = "'check_in_work','check_out_work','check_in_break','check_out_break','unclassified'"
OLD_HINT_TYPES = "'check_in_work','check_out_work','check_in_break','check_out_break'"


def upgrade() -> None:
    op.drop_constraint("ck_punch_type", "attendance_logs", type_="check")
    op.create_check_constraint(
        "ck_punch_type",
        "attendance_logs",
        f"punch_type in ({PUNCH_TYPES}) or punch_type is null",
    )
    op.drop_constraint("ck_punch_type_hint", "attendance_logs", type_="check")
    op.create_check_constraint(
        "ck_punch_type_hint",
        "attendance_logs",
        f"punch_type_hint in ({HINT_TYPES}) or punch_type_hint is null",
    )


def downgrade() -> None:
    # Fold the new kinds back into the work pair they used to be recorded as,
    # so existing rows still satisfy the narrower constraint. The distinction
    # is lost, not the punch.
    op.execute("UPDATE attendance_logs SET punch_type = 'check_in_work' WHERE punch_type = 'check_in_overtime'")
    op.execute("UPDATE attendance_logs SET punch_type = 'check_out_work' WHERE punch_type = 'check_out_overtime'")
    op.execute(
        "UPDATE attendance_logs SET punch_type_hint = 'check_in_work' WHERE punch_type_hint = 'check_in_overtime'"
    )
    op.execute(
        "UPDATE attendance_logs SET punch_type_hint = 'check_out_work' WHERE punch_type_hint = 'check_out_overtime'"
    )
    op.drop_constraint("ck_punch_type", "attendance_logs", type_="check")
    op.create_check_constraint(
        "ck_punch_type", "attendance_logs", f"punch_type in ({OLD_PUNCH_TYPES}) or punch_type is null"
    )
    op.drop_constraint("ck_punch_type_hint", "attendance_logs", type_="check")
    op.create_check_constraint(
        "ck_punch_type_hint",
        "attendance_logs",
        f"punch_type_hint in ({OLD_HINT_TYPES}) or punch_type_hint is null",
    )
