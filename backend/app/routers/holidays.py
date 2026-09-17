"""Public holiday calendar — added 2026-09-17 (migration 0013).

Same access shape as /config: a manager may manage holidays for their own
location, and `assert_location_access` blocks them from touching an org-wide
row (`location_id` NULL), which only an admin can create. Changing the
calendar changes payroll for those dates, so every write returns the affected
date range and callers are expected to re-run /attendance/recompute for it —
the endpoints do not recompute silently, because a holiday added for next
year should not rewrite last month's finished figures on its own.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_location_access, require_manager_or_admin
from app.models import Holiday, User
from app.schemas import HolidayCreate, HolidayOut, HolidayUpdate

router = APIRouter(prefix="/holidays", tags=["holidays"], dependencies=[Depends(require_manager_or_admin)])


def _serialize(row: Holiday) -> HolidayOut:
    out = HolidayOut.model_validate(row)
    out.location_name = row.location.name if row.location else None
    return out


def _get_or_404(db: Session, holiday_id: int) -> Holiday:
    row = db.get(Holiday, holiday_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holiday not found")
    return row


def _assert_unique(db: Session, location_id: int | None, holiday_date: date, exclude_id: int | None = None):
    q = db.query(Holiday).filter(Holiday.holiday_date == holiday_date)
    q = q.filter(Holiday.location_id.is_(None)) if location_id is None else q.filter(
        Holiday.location_id == location_id
    )
    if exclude_id is not None:
        q = q.filter(Holiday.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A holiday already exists on that date for this location",
        )


@router.get("", response_model=list[HolidayOut])
def list_holidays(
    year: int | None = None,
    location_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    q = db.query(Holiday)
    if user.role == "manager":
        # Their location's own entries plus the org-wide ones that apply to
        # them, mirroring /config's scoping.
        q = q.filter(or_(Holiday.location_id == user.location_id, Holiday.location_id.is_(None)))
    if location_id is not None:
        q = q.filter(Holiday.location_id == location_id)
    rows = q.order_by(Holiday.holiday_date).all()
    if year is not None:
        # Recurring entries belong to every year, so they are kept whatever
        # the filter says and shown at their stored month/day.
        rows = [r for r in rows if r.recurs_annually or r.holiday_date.year == year]
    return [_serialize(r) for r in rows]


@router.post("", response_model=HolidayOut, status_code=status.HTTP_201_CREATED)
def create_holiday(payload: HolidayCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    assert_location_access(user, payload.location_id)
    _assert_unique(db, payload.location_id, payload.holiday_date)
    row = Holiday(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.put("/{holiday_id}", response_model=HolidayOut)
def update_holiday(
    holiday_id: int,
    payload: HolidayUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    row = _get_or_404(db, holiday_id)
    assert_location_access(user, row.location_id)
    data = payload.model_dump(exclude_unset=True)
    if "location_id" in data:
        # Checked on the INCOMING value too: without this a manager could
        # move a holiday of their own to org-wide and change every location's
        # payroll.
        assert_location_access(user, data["location_id"])
    _assert_unique(
        db,
        data.get("location_id", row.location_id),
        data.get("holiday_date", row.holiday_date),
        exclude_id=holiday_id,
    )
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holiday(holiday_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    row = _get_or_404(db, holiday_id)
    assert_location_access(user, row.location_id)
    db.delete(row)
    db.commit()
