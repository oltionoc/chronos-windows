"""Nightly daily-status computation — BLUEPRINT.md Section 5.4.

One implementation, two triggers: the `worker`-scheduled nightly job (via
`POST /internal/process/daily-status`) and the manual
`POST /attendance/recompute` endpoint both call `recompute_range` below.

ASSUMPTION (BLUEPRINT.md Section 5.4 does not fully specify this): when
`overtime_config.threshold_basis = 'weekly'`, the per-day `overtime_minutes`
stored here is the raw minutes worked beyond `scheduled_end` (no threshold
subtracted) — the weekly threshold is instead subtracted once per ISO week
during payroll aggregation (`services/payroll_calc.py`), since a single day
cannot know its week's running total in isolation. When
`threshold_basis = 'daily'`, `daily_threshold_minutes` is subtracted here,
at the day level, matching BLUEPRINT's literal wording ("time beyond
scheduled_end + configured overtime threshold").
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttendanceDailyStatus, AttendanceLog, Employee, LeaveRecord, OvertimeConfig
from app.services.classify import classify_employee_date
from app.services.config_lookup import get_effective_config
from app.services.holiday_lookup import get_holiday
from app.services.shift_lookup import (
    get_effective_shift_schedule,
    get_employee_timezone,
    get_schedule_day,
    get_work_windows,
)


def recompute_range(db: Session, date_from: date, date_to: date, employee_id: int | None = None) -> int:
    stmt = select(Employee)
    if employee_id is not None:
        stmt = stmt.where(Employee.id == employee_id)
    else:
        stmt = stmt.where(Employee.employment_status == "active")
    employees = db.execute(stmt).scalars().all()

    count = 0
    d = date_from
    while d <= date_to:
        for emp in employees:
            recompute_employee_date(db, emp.id, d)
            count += 1
        d += timedelta(days=1)
    db.commit()
    return count


def _local_dt(d: date, t, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=tz)


def recompute_employee_date(db: Session, employee_id: int, work_date: date) -> AttendanceDailyStatus:
    existing = db.execute(
        select(AttendanceDailyStatus).where(
            AttendanceDailyStatus.employee_id == employee_id,
            AttendanceDailyStatus.work_date == work_date,
        )
    ).scalar_one_or_none()
    next_version = (existing.recompute_version + 1) if existing else 1

    result = _compute(db, employee_id, work_date)
    result["recompute_version"] = next_version
    result["computed_at"] = datetime.now(tz=ZoneInfo("UTC"))

    if existing:
        # An approval applies to the exact number of minutes the approver saw.
        # If a later punch (or a schedule change) moves that number, the
        # approval is void and has to be given again against the new figure —
        # otherwise a day approved at 20 minutes could silently pay out 200.
        if existing.overtime_approved_at is not None and existing.overtime_minutes != result["overtime_minutes"]:
            result["overtime_approved_at"] = None
            result["overtime_approved_by_user_id"] = None
        for k, v in result.items():
            setattr(existing, k, v)
        row = existing
    else:
        row = AttendanceDailyStatus(employee_id=employee_id, work_date=work_date, **result)
        db.add(row)
    db.flush()
    return row


def _compute(db: Session, employee_id: int, work_date: date) -> dict:
    tz = ZoneInfo(get_employee_timezone(db, employee_id))
    schedule = get_effective_shift_schedule(db, employee_id, work_date)

    if schedule is None:
        return _blank_result(status="not_scheduled")

    day = get_schedule_day(db, schedule, work_date)
    if day is None or not day.is_working_day:
        return _blank_result(status="not_scheduled", shift_schedule_id=schedule.id)

    # A weekday can hold several work blocks (split shift). The stored
    # scheduled_start/scheduled_end stay the day's OUTER bounds — that is what
    # the attendance table, the payslip and the "not checked in" alert all
    # want to show — while late/early/overtime are computed per block below
    # and summed.
    windows = get_work_windows(db, day)
    scheduled_start = windows[0][0] if windows else day.work_start_time
    scheduled_end = windows[-1][1] if windows else day.work_end_time

    # Step 2b: a public holiday replaces the working day entirely. Checked
    # BEFORE leave on purpose: a public holiday falling inside someone's
    # annual leave should not eat a leave day, which is how it works in
    # practice and how the payroll aggregation below reads it (a 'holiday'
    # row is neither an absence nor a leave day).
    employee = db.get(Employee, employee_id)
    holiday = get_holiday(db, employee.location_id if employee else None, work_date)
    if holiday is not None:
        return _holiday_result(
            db,
            employee_id,
            work_date,
            tz,
            schedule,
            scheduled_start,
            scheduled_end,
        )

    # Step 3: approved leave overlapping this date takes precedence over punches.
    leave = db.execute(
        select(LeaveRecord).where(
            LeaveRecord.employee_id == employee_id,
            LeaveRecord.status == "approved",
            LeaveRecord.start_date <= work_date,
            LeaveRecord.end_date >= work_date,
        )
    ).scalar_one_or_none()
    if leave is not None:
        return _blank_result(
            status="on_leave",
            shift_schedule_id=schedule.id,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
        )

    # Step 4: classify (using the currently-effective schedule) then read punches.
    classify_employee_date(db, employee_id, work_date)
    db.flush()

    stmt = (
        select(AttendanceLog)
        .where(AttendanceLog.employee_id == employee_id)
        .order_by(AttendanceLog.punch_timestamp)
    )
    all_logs = db.execute(stmt).scalars().all()
    day_logs = [log for log in all_logs if log.punch_timestamp.astimezone(tz).date() == work_date]

    work_in = [l for l in day_logs if l.punch_type == "check_in_work"]
    work_out = [l for l in day_logs if l.punch_type == "check_out_work"]
    break_in = [l for l in day_logs if l.punch_type == "check_in_break"]
    break_out = [l for l in day_logs if l.punch_type == "check_out_break"]

    # Someone who only badged overtime was still at work, so they are not
    # absent — but those punches sit outside the shift and must not drive the
    # late/early math below, which is why they are kept out of work_in/out.
    presence = [
        l
        for l in day_logs
        if l.punch_type in ("check_in_work", "check_out_work", "check_in_overtime", "check_out_overtime")
    ]
    if not presence:
        return _blank_result(
            status="absent",
            shift_schedule_id=schedule.id,
            scheduled_start=scheduled_start,
            scheduled_end=scheduled_end,
        )

    actual_first_in = work_in[0].punch_timestamp if work_in else min(l.punch_timestamp for l in presence)
    actual_last_out = work_out[-1].punch_timestamp if work_out else max(l.punch_timestamp for l in presence)

    grace = schedule.grace_minutes_late or 0
    late_minutes, early_departure_minutes, raw_overtime = _window_deltas(
        windows, work_date, tz, grace, work_in, work_out
    )

    overtime_minutes = 0
    if raw_overtime > 0:
        ot_config = get_effective_config(db, OvertimeConfig, schedule.location_id, work_date)
        if ot_config is not None and ot_config.threshold_basis == "daily":
            threshold = ot_config.daily_threshold_minutes or 0
            overtime_minutes = max(0, raw_overtime - threshold)
        else:
            # weekly basis (or no config yet) — store raw minutes; weekly
            # threshold subtracted once at payroll aggregation time.
            overtime_minutes = raw_overtime

    # Overtime the employee explicitly badged on the device ("start overtime"
    # / "end overtime") is added WITHOUT the daily threshold. The threshold
    # exists to ignore someone drifting past the end of their shift; pressing
    # the overtime key is not drift, so there is nothing to filter, and
    # shaving it off deliberate overtime just produces a dispute. The
    # pre-approval flag still gates whether any of it is paid.
    overtime_minutes += _badged_overtime_minutes(day_logs)

    # BREAK CANON (see services/classify.py): check_out_break is punching OUT
    # for the break, check_in_break is punching back IN, so a break's duration
    # is return minus departure. This used to subtract the other way round,
    # which meant any break carrying the device's own explicit break codes
    # failed the ordering test and silently contributed 0 minutes.
    break_minutes_taken = 0
    for departure, ret in zip(break_out, break_in):
        if ret.punch_timestamp > departure.punch_timestamp:
            break_minutes_taken += int((ret.punch_timestamp - departure.punch_timestamp).total_seconds() // 60)

    status = "late" if late_minutes > 0 else "present"

    return {
        "shift_schedule_id": schedule.id,
        "scheduled_start": scheduled_start,
        "scheduled_end": scheduled_end,
        "actual_first_in": actual_first_in,
        "actual_last_out": actual_last_out,
        "late_minutes": late_minutes,
        "early_departure_minutes": early_departure_minutes,
        "overtime_minutes": overtime_minutes,
        "break_minutes_taken": break_minutes_taken,
        "status": status,
        "is_absence_excused": None,
    }


def _badged_overtime_minutes(day_logs: list) -> int:
    """Minutes between explicit overtime punches, paired in order.

    An unclosed overtime punch contributes nothing rather than running to the
    end of the day — the same rule the rest of this module uses for a missing
    punch, which is surfaced as an alert instead of silently becoming money.
    """
    starts = [l for l in day_logs if l.punch_type == "check_in_overtime"]
    ends = [l for l in day_logs if l.punch_type == "check_out_overtime"]
    minutes = 0
    for start, end in zip(starts, ends):
        if end.punch_timestamp > start.punch_timestamp:
            minutes += int((end.punch_timestamp - start.punch_timestamp).total_seconds() // 60)
    return minutes


def _holiday_result(
    db: Session,
    employee_id: int,
    work_date: date,
    tz: ZoneInfo,
    schedule,
    scheduled_start,
    scheduled_end,
) -> dict:
    """A public holiday on what would otherwise be a working day.

    Nobody is late, nobody is absent, and no leave day is consumed. If the
    employee DID work, all of it is holiday work: the minutes land in
    `overtime_minutes`, which is what payroll pays at
    `overtime_config.holiday_rate_per_hour_eur` (see services/payroll_calc.py).
    Breaks are subtracted the same way they are on an ordinary day."""
    classify_employee_date(db, employee_id, work_date)
    db.flush()

    all_logs = db.execute(
        select(AttendanceLog)
        .where(AttendanceLog.employee_id == employee_id)
        .order_by(AttendanceLog.punch_timestamp)
    ).scalars().all()
    day_logs = [log for log in all_logs if log.punch_timestamp.astimezone(tz).date() == work_date]

    work_in = [l for l in day_logs if l.punch_type == "check_in_work"]
    work_out = [l for l in day_logs if l.punch_type == "check_out_work"]
    break_in = [l for l in day_logs if l.punch_type == "check_in_break"]
    break_out = [l for l in day_logs if l.punch_type == "check_out_break"]

    worked_minutes = 0
    for start, end in zip(work_in, work_out):
        if end.punch_timestamp > start.punch_timestamp:
            worked_minutes += int((end.punch_timestamp - start.punch_timestamp).total_seconds() // 60)

    break_minutes_taken = 0
    for departure, ret in zip(break_out, break_in):
        if ret.punch_timestamp > departure.punch_timestamp:
            break_minutes_taken += int((ret.punch_timestamp - departure.punch_timestamp).total_seconds() // 60)

    return {
        "shift_schedule_id": schedule.id,
        "scheduled_start": scheduled_start,
        "scheduled_end": scheduled_end,
        "actual_first_in": work_in[0].punch_timestamp if work_in else None,
        "actual_last_out": work_out[-1].punch_timestamp if work_out else None,
        "late_minutes": 0,
        "early_departure_minutes": 0,
        # Work badged as overtime on a holiday is still holiday work, counted
        # once — the punch types are disjoint, so this cannot double-count.
        "overtime_minutes": max(0, worked_minutes - break_minutes_taken) + _badged_overtime_minutes(day_logs),
        "break_minutes_taken": break_minutes_taken,
        "status": "holiday",
        "is_absence_excused": None,
    }


def _window_deltas(
    windows: list,
    work_date: date,
    tz: ZoneInfo,
    grace: int,
    work_in: list,
    work_out: list,
) -> tuple[int, int, int]:
    """Late / early-departure / raw-overtime minutes, summed over the day's
    work blocks.

    Each work punch belongs to exactly one block: the day is cut at the
    midpoint between consecutive blocks, so a punch is judged against the
    block it is nearest to. With a single block (every ordinary schedule)
    every punch lands in it and this reduces to the original day-level math.

    A block nobody punched for produces nothing — no lateness, no early
    departure. Same principle as the missing-check-out rule below: absent
    punches are surfaced as alerts, never silently converted into a payroll
    penalty.
    """
    if not windows:
        return 0, 0, 0

    boundaries = []
    for i in range(len(windows) - 1):
        block_end = _local_dt(work_date, windows[i][1], tz)
        next_start = _local_dt(work_date, windows[i + 1][0], tz)
        boundaries.append(block_end + (next_start - block_end) / 2)

    def block_index(punch_dt: datetime) -> int:
        local = punch_dt.astimezone(tz)
        for i, boundary in enumerate(boundaries):
            if local <= boundary:
                return i
        return len(windows) - 1

    late = 0
    early = 0
    overtime = 0
    for i, (start_time, end_time) in enumerate(windows):
        ins = [l for l in work_in if block_index(l.punch_timestamp) == i]
        outs = [l for l in work_out if block_index(l.punch_timestamp) == i]
        if not ins and not outs:
            continue

        first_in = ins[0].punch_timestamp if ins else outs[0].punch_timestamp
        start_threshold = _local_dt(work_date, start_time, tz) + timedelta(minutes=grace)
        if first_in > start_threshold:
            late += int((first_in - start_threshold).total_seconds() // 60)

        # early_departure/overtime require a real check-out punch. Without one,
        # the last punch we DO have is often just the check-in itself, which
        # would be misread as leaving hours early — a forgotten badge-out must
        # never silently produce a penalty. The missing punch is surfaced
        # separately via /reports/alerts.
        if not outs:
            continue
        last_out = outs[-1].punch_timestamp
        end_dt = _local_dt(work_date, end_time, tz)
        if last_out < end_dt:
            early += int((end_dt - last_out).total_seconds() // 60)
        elif last_out > end_dt:
            overtime += int((last_out - end_dt).total_seconds() // 60)

    return late, early, overtime


def _blank_result(
    status: str,
    shift_schedule_id: int | None = None,
    scheduled_start=None,
    scheduled_end=None,
) -> dict:
    return {
        "shift_schedule_id": shift_schedule_id,
        "scheduled_start": scheduled_start,
        "scheduled_end": scheduled_end,
        "actual_first_in": None,
        "actual_last_out": None,
        "late_minutes": 0,
        "early_departure_minutes": 0,
        "overtime_minutes": 0,
        "break_minutes_taken": 0,
        "status": status,
        "is_absence_excused": None,
    }
