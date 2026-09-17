"""Public-holiday resolution — added 2026-09-17 with migration 0013.

A date is a holiday for an employee when a row exists either for their own
location or org-wide (`location_id IS NULL`, same convention as the config
tables), matching the date exactly, or matching day-and-month when the row is
marked `recurs_annually`.

A location-specific row wins over an org-wide one for the same date, so a
single location can override the national calendar (a town holiday, or a
branch that stays open) without touching the org-wide entry.
"""
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Holiday


def get_holiday(db: Session, location_id: int | None, work_date: date) -> Holiday | None:
    rows = db.execute(
        select(Holiday).where(
            or_(Holiday.location_id == location_id, Holiday.location_id.is_(None)),
            or_(
                Holiday.holiday_date == work_date,
                Holiday.recurs_annually.is_(True),
            ),
        )
    ).scalars().all()

    matches = [
        row
        for row in rows
        if row.holiday_date == work_date
        or (
            row.recurs_annually
            and row.holiday_date.month == work_date.month
            and row.holiday_date.day == work_date.day
        )
    ]
    if not matches:
        return None
    # Location-specific beats org-wide.
    matches.sort(key=lambda h: (h.location_id is None, h.id))
    return matches[0]


def holiday_dates_in_range(db: Session, location_id: int | None, date_from: date, date_to: date) -> set[date]:
    """Every holiday date in [date_from, date_to] for this location.

    Payroll walks a month of daily-status rows and would otherwise ask the
    same question thirty times; this answers it once. Recurring rows are
    expanded across whatever years the range spans."""
    rows = db.execute(
        select(Holiday).where(or_(Holiday.location_id == location_id, Holiday.location_id.is_(None)))
    ).scalars().all()

    found: set[date] = set()
    for row in rows:
        if row.recurs_annually:
            for year in range(date_from.year, date_to.year + 1):
                try:
                    candidate = row.holiday_date.replace(year=year)
                except ValueError:
                    # 29 February on a non-leap year: that date simply does
                    # not occur, so it is not a holiday that year.
                    continue
                if date_from <= candidate <= date_to:
                    found.add(candidate)
        elif date_from <= row.holiday_date <= date_to:
            found.add(row.holiday_date)
    return found
