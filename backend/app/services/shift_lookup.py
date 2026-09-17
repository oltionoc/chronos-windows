"""Shared helpers for resolving the shift schedule/day in effect for an
employee on a given date — used by both punch classification and nightly
daily-status computation (BLUEPRINT.md Sections 5.3/5.4).

An employee may hold SEVERAL assignments covering the same dates, as long as
the schedules behind them claim different weekdays (e.g. "Cafe Shift" working
Mon-Tue and "Office Shift" working Wed-Fri, both open-ended). That is what
`_assert_no_conflict` in routers/employees.py enforces on write, and what the
weekday-aware resolution below relies on for reads: for a given date, the
assignment that wins is the one whose schedule actually marks that weekday as
a working day.
"""
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Employee,
    EmployeeShiftAssignment,
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftWorkWindow,
)


def _covering_assignments(db: Session, employee_id: int, work_date: date) -> list[EmployeeShiftAssignment]:
    stmt = (
        select(EmployeeShiftAssignment)
        .where(
            EmployeeShiftAssignment.employee_id == employee_id,
            EmployeeShiftAssignment.effective_from <= work_date,
        )
        .where(
            (EmployeeShiftAssignment.effective_to.is_(None))
            | (EmployeeShiftAssignment.effective_to > work_date)
        )
        .order_by(
            EmployeeShiftAssignment.effective_from.desc(),
            EmployeeShiftAssignment.id.desc(),
        )
    )
    return list(db.execute(stmt).scalars().all())


def get_effective_shift_schedule(db: Session, employee_id: int, work_date: date) -> ShiftSchedule | None:
    """The schedule governing `work_date`.

    With one assignment this is simply that assignment's schedule (the
    behaviour before split/parallel shifts existed). With several overlapping
    assignments, the one whose schedule marks this weekday as working wins;
    the write-side conflict check guarantees at most one does. If none claims
    the weekday, the most recent covering assignment is still returned so the
    day reads as "not scheduled" against a known schedule rather than as
    having no schedule at all.
    """
    assignments = _covering_assignments(db, employee_id, work_date)
    if not assignments:
        return None

    day_of_week = work_date.weekday()
    fallback: ShiftSchedule | None = None
    for assignment in assignments:
        schedule = db.get(ShiftSchedule, assignment.shift_schedule_id)
        if schedule is None:
            continue
        if fallback is None:
            fallback = schedule
        day = db.execute(
            select(ShiftScheduleDay).where(
                ShiftScheduleDay.shift_schedule_id == schedule.id,
                ShiftScheduleDay.day_of_week == day_of_week,
            )
        ).scalar_one_or_none()
        if day is not None and day.is_working_day:
            return schedule
    return fallback


def get_schedule_day(db: Session, schedule: ShiftSchedule, work_date: date) -> ShiftScheduleDay | None:
    day_of_week = work_date.weekday()  # Monday = 0, matches BLUEPRINT.md 3.5
    stmt = select(ShiftScheduleDay).where(
        ShiftScheduleDay.shift_schedule_id == schedule.id,
        ShiftScheduleDay.day_of_week == day_of_week,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_work_windows(db: Session, day: ShiftScheduleDay | None) -> list[tuple[time, time]]:
    """The day's work blocks as (start, end) pairs, earliest first.

    A day normally has one. Split shifts have several. Falls back to the day's
    own derived `work_start_time`/`work_end_time` when no window rows exist,
    so a schedule written by an older client (or a row that predates
    migration 0011's backfill for any reason) still computes rather than
    silently reporting zero worked time.
    """
    if day is None or not day.is_working_day:
        return []
    rows = db.execute(
        select(ShiftWorkWindow)
        .where(ShiftWorkWindow.shift_schedule_day_id == day.id)
        .order_by(ShiftWorkWindow.sort_order, ShiftWorkWindow.work_start_time)
    ).scalars().all()
    windows = [(r.work_start_time, r.work_end_time) for r in rows if r.work_start_time and r.work_end_time]
    if not windows and day.work_start_time and day.work_end_time:
        windows = [(day.work_start_time, day.work_end_time)]
    windows.sort(key=lambda w: w[0])
    return windows


def get_employee_timezone(db: Session, employee_id: int) -> str:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.location is None:
        return "Europe/Tirane"
    return employee.location.timezone or "Europe/Tirane"
