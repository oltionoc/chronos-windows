"""Punch classification — BLUEPRINT.md Section 5.3.

Runs in `api` (not `worker`) so it can be corrected/replayed without
re-syncing, as specified. Called by the internal ingestion endpoint after
new punches are inserted for an employee/date, and again by
`/attendance/recompute` before daily-status computation so a late shift
re-assignment reclassifies already-stored punches.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendanceLog
from app.services.shift_lookup import (
    resolve_day,
    get_effective_shift_schedule,
    get_employee_timezone,
    get_schedule_day,
)

BREAK_OUT_CODE = 2
BREAK_IN_CODE = 3
# Both vendors can label overtime themselves: ZKTeco emits punch codes 4/5,
# Hikvision reports attendanceStatus overtimeIn/overtimeOut (which the
# adapter encodes as these same codes). Unlike breaks, the IN comes first —
# you start overtime, then end it.
OVERTIME_IN_CODE = 4
OVERTIME_OUT_CODE = 5


def classify_employee_date(db: Session, employee_id: int, work_date: date) -> None:
    stmt = (
        select(AttendanceLog)
        .where(AttendanceLog.employee_id == employee_id)
        .order_by(AttendanceLog.punch_timestamp)
    )
    all_logs = db.execute(stmt).scalars().all()
    tz = ZoneInfo(get_employee_timezone(db, employee_id))
    logs = [log for log in all_logs if log.punch_timestamp.astimezone(tz).date() == work_date]
    if not logs:
        return

    resolved = resolve_day(db, employee_id, work_date)
    if not resolved.scheduled and resolved.source == "none":
        for log in logs:
            log.punch_type = "unclassified"
        return

    break_windows = resolved.break_windows

    def in_break_window(local_time) -> bool:
        return any(bw.start <= local_time <= bw.end for bw in break_windows)

    work_bucket: list[AttendanceLog] = []
    break_bucket: list[AttendanceLog] = []
    overtime_bucket: list[AttendanceLog] = []

    for log in logs:
        # A vendor that already tells us the punch kind (e.g. Hikvision
        # ISAPI's attendanceStatus) is trusted directly — skip the
        # ZKTeco-shaped alternating-parity/break-window inference entirely.
        if log.punch_type_hint is not None:
            log.punch_type = log.punch_type_hint
            continue
        if log.raw_status_code == BREAK_OUT_CODE or log.raw_status_code == BREAK_IN_CODE:
            break_bucket.append(log)
            continue
        # Overtime is never inferred from a time window the way a break is —
        # there is no "overtime window" in a schedule. It only exists when the
        # device says so, so an overtime code is the sole way into this bucket.
        if log.raw_status_code == OVERTIME_IN_CODE or log.raw_status_code == OVERTIME_OUT_CODE:
            overtime_bucket.append(log)
            continue
        local_time = log.punch_timestamp.astimezone(tz).time()
        if in_break_window(local_time):
            break_bucket.append(log)
        else:
            work_bucket.append(log)

    _assign_alternating(work_bucket, first="check_in_work", second="check_out_work")
    # BREAK CANON: `check_out_break` is punching OUT for a break (happens
    # first), `check_in_break` is punching back IN (second). That matches what
    # ZKTeco's codes and Hikvision's breakOut/breakIn labels already mean, and
    # what reports.py's on-break-now and stuck-on-break checks assume. The
    # inferred path used to label these the other way round, which cancelled
    # out against an equally-inverted subtraction in recompute.py and silently
    # produced 0 break minutes as soon as a device supplied explicit codes.
    _assign_alternating(
        break_bucket,
        first="check_out_break",
        second="check_in_break",
        code_overrides={BREAK_IN_CODE: "check_in_break", BREAK_OUT_CODE: "check_out_break"},
    )
    # Overtime runs the other way round from a break: the IN is first.
    _assign_alternating(
        overtime_bucket,
        first="check_in_overtime",
        second="check_out_overtime",
        code_overrides={
            OVERTIME_IN_CODE: "check_in_overtime",
            OVERTIME_OUT_CODE: "check_out_overtime",
        },
    )


def _assign_alternating(
    bucket: list[AttendanceLog],
    first: str,
    second: str,
    code_overrides: dict[int, str] | None = None,
) -> None:
    """Labels a chronologically-sorted bucket by alternating position. The
    params are named for POSITION, not semantics — they used to be `check_in`
    /`check_out`, which invited the break bucket being labelled in the wrong
    order (see the break canon documented above)."""
    bucket.sort(key=lambda l: l.punch_timestamp)
    for i, log in enumerate(bucket):
        if code_overrides and log.raw_status_code in code_overrides:
            log.punch_type = code_overrides[log.raw_status_code]
        else:
            # Odd-numbered occurrences (1st, 3rd, ...) are the outbound half
            log.punch_type = first if i % 2 == 0 else second
