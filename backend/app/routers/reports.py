from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import false, func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import (
    AttendanceDailyStatus,
    AttendanceLog,
    Device,
    Employee,
    LeaveRecord,
    OvertimeConfig,
    User,
)
from app.routers.leave import _serialize as serialize_leave
from app.services.config_lookup import get_effective_config
from app.services.shift_lookup import (
    get_effective_shift_schedule,
    get_employee_timezone,
    get_schedule_day,
    get_work_windows,
)
from app.schemas import (
    AlertItem,
    AlertsOut,
    AnalyticsOut,
    AttendanceTrendDay,
    DashboardSummaryOut,
    OnBreakEmployee,
    OnLeaveEmployee,
    TopLateEmployee,
    TopOvertimeEmployee,
)

router = APIRouter(prefix="/reports", tags=["reports"])

# How far outside a day's work blocks a punch may land before it is worth
# flagging. Wide enough that arriving early, staying late, or a schedule
# someone shifted by an hour stays quiet; narrow enough that a punch in the
# middle of the night, or on the wrong day, is not.
OUTSIDE_SCHEDULE_TOLERANCE = timedelta(hours=2)

# How far a device's own clock may sit from the server's before its punches
# stop being trustworthy. Two minutes: below that, the error is smaller than
# any grace period and cannot flip a lateness decision; above it, every punch
# that device sends is wrong by a payroll-relevant amount.
CLOCK_DRIFT_TOLERANCE_SECONDS = 120

# Written by the backup job after every attempt (ops/backup.sh in Docker,
# backup.ps1 on the native Windows install). Read through Settings rather than
# os.environ so the value can come from the same config file as everything
# else — the Windows services load chronos.env, which never reaches os.environ.
BACKUP_MARKER = Path(settings.backup_marker_path)
# A daily schedule plus one missed night. Past this, either the schedule is
# not running or the machine has been off long enough to matter.
BACKUP_MAX_AGE = timedelta(hours=36)


def _backup_alert() -> AlertItem | None:
    """Reads the marker ops/backup.sh writes after every attempt.

    Three outcomes worth telling an admin about: the last attempt failed, the
    last success is too old, or there is no marker at all (the backup service
    was never started — the most dangerous case, because nothing else in the
    app would ever mention it). Returns None when backups are healthy.
    """
    try:
        raw = BACKUP_MARKER.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return AlertItem(
            type="backup_missing",
            severity="danger",
            message="No database backup has ever run — payroll history is not protected",
        )
    except OSError:
        return None

    parts = raw.split()
    stamp = parts[0] if parts else ""
    status_word = parts[1] if len(parts) > 1 else "failed"
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        when = None

    if status_word != "ok":
        return AlertItem(
            type="backup_failed",
            severity="danger",
            message="The last database backup failed",
            occurred_at=when,
        )
    if when is not None and when < datetime.now(timezone.utc) - BACKUP_MAX_AGE:
        hours = int((datetime.now(timezone.utc) - when).total_seconds() // 3600)
        return AlertItem(
            type="backup_stale",
            severity="danger",
            message=f"The last successful database backup is {hours}h old",
            count=hours,
            occurred_at=when,
        )
    return None


def _scope_employee_query(q, user: User, location_id: int | None):
    """Shared location-scoping (BLUEPRINT.md Section 6.2/6.3) for any query
    already joined to Employee — a manager with no assigned location matches
    nothing, fail-closed."""
    if user.role == "manager":
        if user.location_id is None:
            return q.filter(false())
        return q.filter(Employee.location_id == user.location_id)
    if location_id is not None:
        return q.filter(Employee.location_id == location_id)
    return q


def _on_site_now(db: Session, user: User, location_id: int | None, target_date: date_type) -> int:
    """Live headcount, not a daily-status field. Defined as: an employee's
    single most recent punch (ever) happened today and was not a
    check_out_work — i.e. they haven't clocked out for the day (still
    clocked in, or mid-break as part of the same still-open shift). A real
    check-out punch drops them from this count immediately, the same instant
    it's ingested (see internal.py's live recompute)."""
    emp_q = _scope_employee_query(db.query(Employee.id), user, location_id)
    emp_ids = [row[0] for row in emp_q.all()]
    if not emp_ids:
        return 0

    latest = (
        db.query(AttendanceLog.employee_id, func.max(AttendanceLog.punch_timestamp).label("max_ts"))
        .filter(AttendanceLog.employee_id.in_(emp_ids))
        .group_by(AttendanceLog.employee_id)
        .subquery()
    )
    latest_logs = (
        db.query(AttendanceLog)
        .join(
            latest,
            (AttendanceLog.employee_id == latest.c.employee_id) & (AttendanceLog.punch_timestamp == latest.c.max_ts),
        )
        .all()
    )

    count = 0
    for log in latest_logs:
        # Either kind of clock-out means they have gone home: someone whose
        # last punch is "end overtime" is no longer on site.
        if log.punch_type in ("check_out_work", "check_out_overtime"):
            continue
        tz = ZoneInfo(get_employee_timezone(db, log.employee_id))
        if log.punch_timestamp.astimezone(tz).date() == target_date:
            count += 1
    return count


def _on_leave_today(db: Session, user: User, location_id: int | None, target_date: date_type) -> list[OnLeaveEmployee]:
    """Who's on approved leave today, and why — separate from
    AttendanceDailyStatus.status == 'on_leave' because that column has no
    room for the reason; this reads LeaveRecord directly so the dashboard
    can show the leave type name, not just the fact of being away."""
    q = (
        db.query(LeaveRecord, Employee)
        .join(Employee, LeaveRecord.employee_id == Employee.id)
        .filter(
            LeaveRecord.status == "approved",
            LeaveRecord.start_date <= target_date,
            LeaveRecord.end_date >= target_date,
        )
    )
    q = _scope_employee_query(q, user, location_id)
    return [
        OnLeaveEmployee(
            employee_id=emp.id,
            employee_name=f"{emp.first_name} {emp.last_name}",
            leave_type_name_en=rec.leave_type.name_en,
            leave_type_name_sq=rec.leave_type.name_sq,
            start_date=rec.start_date,
            end_date=rec.end_date,
        )
        for rec, emp in q.order_by(Employee.first_name, Employee.last_name).all()
    ]


def _on_break_now(db: Session, user: User, location_id: int | None, target_date: date_type) -> list[OnBreakEmployee]:
    """Live list, not a daily-status field — attendance_daily_status is a
    nightly aggregate with no "currently mid-break" concept. Defined as: an
    employee's single most recent punch (ever) is a break-out with no
    following break-in, and that punch happened today in the employee's own
    timezone — the date check keeps someone who forgot to punch back in
    yesterday from showing as "on break" forever."""
    emp_q = _scope_employee_query(db.query(Employee.id, Employee.first_name, Employee.last_name), user, location_id)
    emp_rows = {row[0]: f"{row[1]} {row[2]}" for row in emp_q.all()}
    if not emp_rows:
        return []

    latest = (
        db.query(AttendanceLog.employee_id, func.max(AttendanceLog.punch_timestamp).label("max_ts"))
        .filter(AttendanceLog.employee_id.in_(list(emp_rows)))
        .group_by(AttendanceLog.employee_id)
        .subquery()
    )
    latest_logs = (
        db.query(AttendanceLog)
        .join(
            latest,
            (AttendanceLog.employee_id == latest.c.employee_id) & (AttendanceLog.punch_timestamp == latest.c.max_ts),
        )
        .all()
    )

    result: list[OnBreakEmployee] = []
    for log in latest_logs:
        if log.punch_type != "check_out_break":
            continue
        tz = ZoneInfo(get_employee_timezone(db, log.employee_id))
        if log.punch_timestamp.astimezone(tz).date() == target_date:
            result.append(
                OnBreakEmployee(
                    employee_id=log.employee_id,
                    employee_name=emp_rows[log.employee_id],
                    break_started_at=log.punch_timestamp,
                )
            )
    return result


@router.get("/dashboard-summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    location_id: int | None = None,
    date: date_type | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target_date = date or date_type.today()

    status_q = db.query(AttendanceDailyStatus).join(Employee, AttendanceDailyStatus.employee_id == Employee.id).filter(
        AttendanceDailyStatus.work_date == target_date
    )
    leave_q = db.query(LeaveRecord).join(Employee, LeaveRecord.employee_id == Employee.id).filter(
        LeaveRecord.status == "pending"
    )

    status_q = _scope_employee_query(status_q, user, location_id)
    leave_q = _scope_employee_query(leave_q, user, location_id)

    # "Present" on the dashboard means "showed up today" — includes late
    # arrivals, since a late employee is still present, just late. "Late" is
    # a separate, overlapping breakdown of who among the present was late,
    # not a third mutually-exclusive bucket. (Analytics' stacked trend chart
    # keeps present/late/absent/on_leave mutually exclusive — that's a
    # different view and untouched here.)
    present_today = status_q.filter(AttendanceDailyStatus.status.in_(("present", "late"))).count()
    late_today = status_q.filter(AttendanceDailyStatus.status == "late").count()
    absent_today = status_q.filter(AttendanceDailyStatus.status == "absent").count()

    pending_total = leave_q.count()
    pending_records = leave_q.order_by(LeaveRecord.start_date).limit(5).all()
    on_break = _on_break_now(db, user, location_id, target_date)
    on_site = _on_site_now(db, user, location_id, target_date)
    on_leave = _on_leave_today(db, user, location_id, target_date)

    return DashboardSummaryOut(
        present_today=present_today,
        on_site_now=on_site,
        late_today=late_today,
        absent_today=absent_today,
        on_leave_today=len(on_leave),
        on_leave_employees=on_leave,
        on_break_now=len(on_break),
        on_break_employees=on_break,
        pending_leave_count=pending_total,
        pending_leave=[serialize_leave(r) for r in pending_records],
        pending_leave_total=pending_total,
    )


@router.get("/analytics", response_model=AnalyticsOut)
def analytics(
    days: int = 14,
    location_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    days = max(1, min(days, 90))
    date_from = date_type.today() - timedelta(days=days - 1)
    date_to = date_type.today()

    status_q = db.query(AttendanceDailyStatus).join(Employee, AttendanceDailyStatus.employee_id == Employee.id).filter(
        AttendanceDailyStatus.work_date >= date_from,
        AttendanceDailyStatus.work_date <= date_to,
    )
    status_q = _scope_employee_query(status_q, user, location_id)

    counts = (
        status_q.with_entities(
            AttendanceDailyStatus.work_date,
            AttendanceDailyStatus.status,
            func.count().label("n"),
        )
        .group_by(AttendanceDailyStatus.work_date, AttendanceDailyStatus.status)
        .all()
    )
    by_date: dict[date_type, dict[str, int]] = {}
    d = date_from
    while d <= date_to:
        by_date[d] = {"present": 0, "late": 0, "absent": 0, "on_leave": 0}
        d += timedelta(days=1)
    for work_date, status_value, n in counts:
        if work_date in by_date and status_value in by_date[work_date]:
            by_date[work_date][status_value] = n

    trend = [
        AttendanceTrendDay(work_date=d, present=v["present"], late=v["late"], absent=v["absent"], on_leave=v["on_leave"])
        for d, v in sorted(by_date.items())
    ]

    avg_late = status_q.filter(AttendanceDailyStatus.late_minutes > 0).with_entities(
        func.avg(AttendanceDailyStatus.late_minutes)
    ).scalar()
    total_overtime = status_q.with_entities(func.coalesce(func.sum(AttendanceDailyStatus.overtime_minutes), 0)).scalar()

    late_q = (
        db.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            func.sum(AttendanceDailyStatus.late_minutes).label("total_late"),
            func.count(AttendanceDailyStatus.id).label("late_days"),
        )
        .join(AttendanceDailyStatus, AttendanceDailyStatus.employee_id == Employee.id)
        .filter(
            AttendanceDailyStatus.work_date >= date_from,
            AttendanceDailyStatus.work_date <= date_to,
            AttendanceDailyStatus.status == "late",
        )
    )
    late_q = _scope_employee_query(late_q, user, location_id)
    top_late = (
        late_q.group_by(Employee.id, Employee.first_name, Employee.last_name)
        .order_by(func.sum(AttendanceDailyStatus.late_minutes).desc())
        .limit(5)
        .all()
    )

    overtime_q = (
        db.query(
            Employee.id,
            Employee.first_name,
            Employee.last_name,
            func.sum(AttendanceDailyStatus.overtime_minutes).label("total_overtime"),
            func.count(AttendanceDailyStatus.id).label("overtime_days"),
        )
        .join(AttendanceDailyStatus, AttendanceDailyStatus.employee_id == Employee.id)
        .filter(
            AttendanceDailyStatus.work_date >= date_from,
            AttendanceDailyStatus.work_date <= date_to,
            AttendanceDailyStatus.overtime_minutes > 0,
        )
    )
    overtime_q = _scope_employee_query(overtime_q, user, location_id)
    top_overtime = (
        overtime_q.group_by(Employee.id, Employee.first_name, Employee.last_name)
        .order_by(func.sum(AttendanceDailyStatus.overtime_minutes).desc())
        .limit(5)
        .all()
    )

    return AnalyticsOut(
        attendance_trend=trend,
        avg_late_minutes=round(float(avg_late), 1) if avg_late else 0.0,
        total_overtime_minutes=int(total_overtime or 0),
        top_late_employees=[
            TopLateEmployee(
                employee_id=eid,
                employee_name=f"{first} {last}",
                total_late_minutes=int(total_late or 0),
                late_days=late_days,
            )
            for eid, first, last, total_late, late_days in top_late
        ],
        top_overtime_employees=[
            TopOvertimeEmployee(
                employee_id=eid,
                employee_name=f"{first} {last}",
                total_overtime_minutes=int(total_ot or 0),
                overtime_days=overtime_days,
            )
            for eid, first, last, total_ot, overtime_days in top_overtime
        ],
    )


@router.get("/alerts", response_model=AlertsOut)
def alerts(
    days: int = 14,
    location_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Operational anomalies HR (or a location-scoped Manager) should look
    at — things the system detected automatically rather than a business
    number. Not tied to any one page; each item links to where it's fixed."""
    days = max(1, min(days, 90))
    since = date_type.today() - timedelta(days=days - 1)
    items: list[AlertItem] = []

    # Missing checkout: a work day with a real check-in but no distinguishable
    # check-out (recompute.py leaves actual_last_out == actual_first_in in
    # that case specifically so it never masquerades as an early departure —
    # see services/recompute.py). Location-scoped like everything else.
    missing_q = (
        db.query(AttendanceDailyStatus, Employee)
        .join(Employee, AttendanceDailyStatus.employee_id == Employee.id)
        .filter(
            AttendanceDailyStatus.work_date >= since,
            AttendanceDailyStatus.status.in_(["present", "late"]),
            AttendanceDailyStatus.actual_first_in.isnot(None),
            AttendanceDailyStatus.actual_last_out == AttendanceDailyStatus.actual_first_in,
        )
    )
    missing_q = _scope_employee_query(missing_q, user, location_id)
    for status_row, emp in missing_q.order_by(AttendanceDailyStatus.work_date.desc()).limit(50).all():
        items.append(
            AlertItem(
                type="missing_checkout",
                severity="warning",
                message=f"{emp.first_name} {emp.last_name} has no check-out recorded",
                employee_id=emp.id,
                employee_name=f"{emp.first_name} {emp.last_name}",
                work_date=status_row.work_date,
                occurred_at=status_row.actual_first_in,
                link=f"/attendance?status={status_row.status}&date={status_row.work_date}",
            )
        )

    # Stuck on break: more break-outs than break-ins on a given day — a
    # different anomaly from missing_checkout above (that one only looks at
    # the day's final check-out; this catches a break that was never
    # returned from even when the final check-out did happen). Computed from
    # raw punches — attendance_daily_status only stores the aggregate
    # break_minutes_taken, not a count to compare.
    emp_scope_q = _scope_employee_query(
        db.query(Employee.id, Employee.first_name, Employee.last_name), user, location_id
    )
    emp_scope = {row[0]: (row[1], row[2]) for row in emp_scope_q.all()}
    if emp_scope:
        break_logs = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id.in_(list(emp_scope)),
                AttendanceLog.punch_type.in_(["check_in_break", "check_out_break"]),
                AttendanceLog.punch_timestamp >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc),
            )
            .order_by(AttendanceLog.punch_timestamp)
            .all()
        )
        by_emp_day: dict[tuple[int, date_type], dict] = {}
        for log in break_logs:
            tz = ZoneInfo(get_employee_timezone(db, log.employee_id))
            local_date = log.punch_timestamp.astimezone(tz).date()
            key = (log.employee_id, local_date)
            row = by_emp_day.setdefault(key, {"out": 0, "in": 0, "last_out": None})
            if log.punch_type == "check_out_break":
                row["out"] += 1
                row["last_out"] = log.punch_timestamp
            else:
                row["in"] += 1
        for (emp_id, work_date), row in by_emp_day.items():
            # Exclude today — someone mid-break right now isn't "stuck" yet,
            # that's the dashboard's on_break_now, a normal in-progress
            # state. This alert is for a break that was never returned from
            # once the day was already over.
            if work_date < date_type.today() and row["out"] > row["in"]:
                first, last = emp_scope[emp_id]
                items.append(
                    AlertItem(
                        type="stuck_on_break",
                        severity="warning",
                        message=f"{first} {last} started a break but never punched back in",
                        employee_id=emp_id,
                        employee_name=f"{first} {last}",
                        work_date=work_date,
                        occurred_at=row["last_out"],
                        link=f"/attendance?status=present&date={work_date}",
                    )
                )

    # Not checked in: scheduled to work today, not on approved leave, no
    # punches yet, and meaningfully past their scheduled start (30-minute
    # buffer so this doesn't fire the second the clock ticks past start
    # time — it's meant to catch a real no-show-so-far, not routine lateness
    # already covered by the "late" status once the day is processed).
    target_date = date_type.today()
    now_utc = datetime.now(timezone.utc)
    not_in_emp_q = _scope_employee_query(db.query(Employee), user, location_id).filter(
        Employee.employment_status == "active"
    )
    for emp in not_in_emp_q.all():
        schedule = get_effective_shift_schedule(db, emp.id, target_date)
        if schedule is None:
            continue
        day = get_schedule_day(db, schedule, target_date)
        if day is None or not day.is_working_day or not day.work_start_time:
            continue

        tz = ZoneInfo(get_employee_timezone(db, emp.id))
        scheduled_start_local = datetime.combine(target_date, day.work_start_time, tzinfo=tz)
        if now_utc < scheduled_start_local.astimezone(timezone.utc) + timedelta(minutes=30):
            continue

        on_leave = (
            db.query(LeaveRecord)
            .filter(
                LeaveRecord.employee_id == emp.id,
                LeaveRecord.status == "approved",
                LeaveRecord.start_date <= target_date,
                LeaveRecord.end_date >= target_date,
            )
            .first()
        )
        if on_leave is not None:
            continue

        has_punch_today = (
            db.query(AttendanceLog.id)
            .filter(
                AttendanceLog.employee_id == emp.id,
                AttendanceLog.punch_timestamp >= datetime.combine(target_date, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc),
            )
            .first()
        )
        if has_punch_today is not None:
            continue

        items.append(
            AlertItem(
                type="not_checked_in",
                severity="danger",
                message=f"{emp.first_name} {emp.last_name} hasn't checked in today and isn't on leave",
                employee_id=emp.id,
                employee_name=f"{emp.first_name} {emp.last_name}",
                work_date=target_date,
                occurred_at=scheduled_start_local.astimezone(timezone.utc),
                link=f"/attendance?status=absent&date={target_date}",
            )
        )

    # Punched outside the schedule: badged on a day nobody is scheduled for,
    # or hours away from any of that day's work blocks. Left as a flag rather
    # than a payroll effect on purpose — the punch is real and stays recorded,
    # but somebody has to say whether it was a swapped shift (assign one), an
    # unscheduled extra day, or a wrong badge. It also catches the ugly class
    # of bug that pays out silently: a device whose clock has drifted to
    # another timezone reports punches at impossible hours, and without this
    # nothing complains until payroll.
    if emp_scope:
        outside_logs = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id.in_(list(emp_scope)),
                AttendanceLog.punch_timestamp >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc),
            )
            .order_by(AttendanceLog.punch_timestamp)
            .all()
        )
        outside_by_emp_day: dict[tuple[int, date_type], dict] = {}
        # One schedule resolution per employee-day, not per punch: this scans
        # every punch of the period for every employee in scope.
        tz_cache: dict[int, ZoneInfo] = {}
        window_cache: dict[tuple[int, date_type], list] = {}
        for log in outside_logs:
            if log.employee_id not in tz_cache:
                tz_cache[log.employee_id] = ZoneInfo(get_employee_timezone(db, log.employee_id))
            tz = tz_cache[log.employee_id]
            local = log.punch_timestamp.astimezone(tz)
            local_date = local.date()
            cache_key = (log.employee_id, local_date)
            if cache_key not in window_cache:
                schedule = get_effective_shift_schedule(db, log.employee_id, local_date)
                window_cache[cache_key] = (
                    get_work_windows(db, get_schedule_day(db, schedule, local_date))
                    if schedule is not None
                    else []
                )
            windows = window_cache[cache_key]
            if windows:
                earliest = datetime.combine(local_date, windows[0][0], tzinfo=tz) - OUTSIDE_SCHEDULE_TOLERANCE
                latest = datetime.combine(local_date, windows[-1][1], tzinfo=tz) + OUTSIDE_SCHEDULE_TOLERANCE
                # A punch in the GAP of a split shift is normal (that is the
                # point of a split shift), so only the day's outer bounds count.
                if earliest <= local <= latest:
                    continue
            row = outside_by_emp_day.setdefault(
                (log.employee_id, local_date), {"count": 0, "first": log.punch_timestamp, "scheduled": bool(windows)}
            )
            row["count"] += 1
        for (emp_id, work_date), row in sorted(outside_by_emp_day.items(), key=lambda kv: kv[0][1], reverse=True)[:50]:
            first, last = emp_scope[emp_id]
            items.append(
                AlertItem(
                    type="punch_outside_schedule",
                    severity="warning",
                    message=(
                        f"{first} {last} punched {row['count']} time(s) outside their scheduled hours"
                        if row["scheduled"]
                        else f"{first} {last} punched {row['count']} time(s) on a day they aren't scheduled to work"
                    ),
                    employee_id=emp_id,
                    employee_name=f"{first} {last}",
                    work_date=work_date,
                    occurred_at=row["first"],
                    count=row["count"],
                    link=f"/attendance/logs?employee_id={emp_id}&date_from={work_date}&date_to={work_date}",
                )
            )

    # Overtime waiting for approval: only raised where the location's overtime
    # config actually requires pre-approval, in which case these minutes pay
    # nothing until someone approves the day (see services/payroll_calc.py).
    # Without this alert that money would just quietly not be paid.
    pending_q = (
        db.query(AttendanceDailyStatus, Employee)
        .join(Employee, AttendanceDailyStatus.employee_id == Employee.id)
        .filter(
            AttendanceDailyStatus.work_date >= since,
            AttendanceDailyStatus.overtime_minutes > 0,
            AttendanceDailyStatus.overtime_approved_at.is_(None),
        )
    )
    pending_q = _scope_employee_query(pending_q, user, location_id)
    preapproval_cache: dict[tuple[int | None, date_type], bool] = {}
    for status_row, emp in pending_q.order_by(AttendanceDailyStatus.work_date.desc()).limit(50).all():
        key = (emp.location_id, status_row.work_date)
        if key not in preapproval_cache:
            cfg = get_effective_config(db, OvertimeConfig, emp.location_id, status_row.work_date)
            preapproval_cache[key] = bool(cfg is not None and cfg.requires_preapproval)
        if not preapproval_cache[key]:
            continue
        items.append(
            AlertItem(
                type="overtime_pending_approval",
                severity="warning",
                message=f"{emp.first_name} {emp.last_name} has {status_row.overtime_minutes} overtime minute(s) awaiting approval",
                employee_id=emp.id,
                employee_name=f"{emp.first_name} {emp.last_name}",
                work_date=status_row.work_date,
                occurred_at=status_row.actual_last_out,
                count=status_row.overtime_minutes,
                link=f"/attendance?date={status_row.work_date}",
            )
        )

    if user.role == "admin":
        # Unresolved punches: device sent a punch for a device_user_id with
        # no matching enrollment. Not location-scopable (no employee yet).
        unresolved_q = db.query(func.count(AttendanceLog.id), func.max(AttendanceLog.punch_timestamp)).filter(
            AttendanceLog.employee_id.is_(None),
            AttendanceLog.punch_timestamp >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc),
        )
        if location_id is not None:
            unresolved_q = unresolved_q.join(Device, AttendanceLog.device_id == Device.id).filter(
                Device.location_id == location_id
            )
        unresolved_count, unresolved_latest = unresolved_q.first()
        unresolved_count = unresolved_count or 0
        if unresolved_count:
            items.append(
                AlertItem(
                    type="unresolved_punches",
                    severity="warning",
                    message=f"{unresolved_count} unresolved punch(es) from unrecognized device users",
                    count=unresolved_count,
                    occurred_at=unresolved_latest,
                    link="/attendance/logs",
                )
            )

        # Devices that haven't synced in over 24h (or never).
        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        device_q = db.query(Device).filter(Device.is_active.is_(True))
        if location_id is not None:
            device_q = device_q.filter(Device.location_id == location_id)
        for device in device_q.all():
            if device.last_synced_at is None or device.last_synced_at < stale_cutoff:
                items.append(
                    AlertItem(
                        type="device_stale",
                        severity="danger",
                        message=f"Device \"{device.label}\" hasn't synced in over 24h",
                        device_label=device.label,
                        occurred_at=device.last_synced_at,
                        link="/devices",
                    )
                )
                continue

            # Clock drift. Danger, not warning: the device stamps every punch
            # it sends, so this much error is already sitting in today's
            # lateness and overtime figures. A stale reading (device offline
            # for a day) is skipped above rather than reported twice.
            if (
                device.clock_skew_seconds is not None
                and abs(device.clock_skew_seconds) > CLOCK_DRIFT_TOLERANCE_SECONDS
            ):
                minutes = round(device.clock_skew_seconds / 60)
                items.append(
                    AlertItem(
                        type="device_clock_drift",
                        severity="danger",
                        message=(
                            f"Device \"{device.label}\" clock is {abs(minutes)} minute(s) "
                            f"{'ahead of' if minutes > 0 else 'behind'} the server — "
                            "punch times are wrong by that much"
                        ),
                        device_label=device.label,
                        count=minutes,
                        occurred_at=device.clock_checked_at,
                        link="/devices",
                    )
                )

        # Backups. The dump runs in its own container (ops/backup.sh) and
        # writes BACKUP_MARKER after each attempt. A backup nobody checks is
        # a backup nobody has: on-premise there is one machine holding every
        # punch and every payroll run, and the failure mode is silence until
        # the day it is needed.
        backup_alert = _backup_alert()
        if backup_alert is not None:
            items.append(backup_alert)

        # Managers with no location assigned — they currently see nothing,
        # per BLUEPRINT.md §6.2's fail-closed rule. Worth HR's attention.
        unassigned = db.query(User).filter(User.role == "manager", User.location_id.is_(None), User.is_active.is_(True)).all()
        for mgr in unassigned:
            items.append(
                AlertItem(
                    type="manager_no_location",
                    severity="warning",
                    message=f"Manager \"{mgr.username}\" has no location assigned — they can't see any data",
                    username=mgr.username,
                    link="/settings/users",
                )
            )

    # Sorted newest-first by the actual event datetime (primary), with
    # danger-before-warning as a tiebreaker. Two stable sorts (severity
    # first, then datetime) since the two need opposite directions
    # (severity ascending, datetime descending). Falls back to work_date at
    # midnight when an alert has no occurred_at, and to the absolute
    # earliest instant when it has neither (e.g. manager_no_location — a
    # standing state, not a moment in time) — those sink to the bottom.
    def _sort_dt(a: AlertItem) -> datetime:
        if a.occurred_at is not None:
            return a.occurred_at
        if a.work_date is not None:
            return datetime.combine(a.work_date, datetime.min.time(), tzinfo=timezone.utc)
        return datetime.min.replace(tzinfo=timezone.utc)

    severity_rank = {"danger": 0, "warning": 1}
    items.sort(key=lambda a: severity_rank[a.severity])
    items.sort(key=_sort_dt, reverse=True)
    return AlertsOut(alerts=items, count=len(items))
