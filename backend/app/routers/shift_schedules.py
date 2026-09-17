from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import false
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import assert_location_access, get_current_user, require_manager_or_admin
from app.models import ShiftBreakWindow, ShiftSchedule, ShiftScheduleDay, ShiftWorkWindow, User
from app.schemas import (
    ShiftScheduleCreate,
    ShiftScheduleDayOut,
    ShiftScheduleDaysReplace,
    ShiftScheduleOut,
    ShiftScheduleUpdate,
)

router = APIRouter(prefix="/shift-schedules", tags=["shift-schedules"], dependencies=[Depends(require_manager_or_admin)])


def _serialize(schedule: ShiftSchedule, include_days: bool = True) -> ShiftScheduleOut:
    out = ShiftScheduleOut.model_validate(schedule)
    out.location_name = schedule.location.name if schedule.location else None
    if not include_days:
        out.days = None
    return out


def _get_schedule_or_404(db: Session, schedule_id: int) -> ShiftSchedule:
    schedule = db.get(ShiftSchedule, schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift schedule not found")
    return schedule


@router.get("", response_model=list[ShiftScheduleOut])
def list_schedules(location_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(ShiftSchedule).options(
        selectinload(ShiftSchedule.days).selectinload(ShiftScheduleDay.break_windows),
        selectinload(ShiftSchedule.days).selectinload(ShiftScheduleDay.work_windows),
    )
    if user.role == "manager":
        if user.location_id is None:
            q = q.filter(false())
        else:
            q = q.filter(ShiftSchedule.location_id == user.location_id)
    if location_id is not None:
        q = q.filter(ShiftSchedule.location_id == location_id)
    return [_serialize(s) for s in q.order_by(ShiftSchedule.name).all()]


@router.post("", response_model=ShiftScheduleOut, status_code=status.HTTP_201_CREATED)
def create_schedule(payload: ShiftScheduleCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_location_access(user, payload.location_id)
    schedule = ShiftSchedule(**payload.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return _serialize(schedule)


@router.get("/{schedule_id}", response_model=ShiftScheduleOut)
def get_schedule(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schedule = _get_schedule_or_404(db, schedule_id)
    assert_location_access(user, schedule.location_id)
    return _serialize(schedule)


@router.put("/{schedule_id}", response_model=ShiftScheduleOut)
def update_schedule(schedule_id: int, payload: ShiftScheduleUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schedule = _get_schedule_or_404(db, schedule_id)
    assert_location_access(user, schedule.location_id)
    data = payload.model_dump(exclude_unset=True)
    if "location_id" in data:
        assert_location_access(user, data["location_id"])
    for k, v in data.items():
        setattr(schedule, k, v)
    db.commit()
    db.refresh(schedule)
    return _serialize(schedule)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    schedule = _get_schedule_or_404(db, schedule_id)
    assert_location_access(user, schedule.location_id)
    db.delete(schedule)
    db.commit()


def _resolve_windows(day_in) -> list[tuple]:
    """The day's work blocks, earliest first.

    A day may arrive either as an explicit `work_windows` list (split shift)
    or as the plain `work_start_time`/`work_end_time` pair that every client
    sent before split shifts existed — the pair is just a one-window day."""
    if not day_in.is_working_day:
        return []
    if day_in.work_windows:
        windows = [(w.work_start_time, w.work_end_time) for w in day_in.work_windows]
    elif day_in.work_start_time and day_in.work_end_time:
        windows = [(day_in.work_start_time, day_in.work_end_time)]
    else:
        return []

    windows.sort(key=lambda w: w[0])
    for start, end in windows:
        if end <= start:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A work block must end after it starts",
            )
    for (_, prev_end), (next_start, _) in zip(windows, windows[1:]):
        if next_start < prev_end:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Work blocks on the same day may not overlap",
            )
    return windows


@router.put("/{schedule_id}/days", response_model=list[ShiftScheduleDayOut])
def replace_days(schedule_id: int, payload: ShiftScheduleDaysReplace, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Bulk replace all shift_schedule_days + nested work/break windows for
    the schedule in one call, per BLUEPRINT.md Section 4.5."""
    schedule = _get_schedule_or_404(db, schedule_id)
    assert_location_access(user, schedule.location_id)

    # Child rows go first, explicitly: the day delete below is a bulk query
    # (no ORM cascade), and shift_break_windows' foreign key carries no
    # ON DELETE, so replacing the days of a schedule that has breaks would
    # otherwise hit a foreign-key violation.
    old_day_ids = [
        row[0]
        for row in db.query(ShiftScheduleDay.id).filter(ShiftScheduleDay.shift_schedule_id == schedule_id).all()
    ]
    if old_day_ids:
        db.query(ShiftBreakWindow).filter(ShiftBreakWindow.shift_schedule_day_id.in_(old_day_ids)).delete(
            synchronize_session=False
        )
        db.query(ShiftWorkWindow).filter(ShiftWorkWindow.shift_schedule_day_id.in_(old_day_ids)).delete(
            synchronize_session=False
        )
    db.query(ShiftScheduleDay).filter(ShiftScheduleDay.shift_schedule_id == schedule_id).delete(
        synchronize_session=False
    )
    db.flush()

    created_days = []
    for day_in in payload.days:
        windows = _resolve_windows(day_in)
        day = ShiftScheduleDay(
            shift_schedule_id=schedule_id,
            day_of_week=day_in.day_of_week,
            is_working_day=day_in.is_working_day,
            # Derived outer bounds — the per-block truth lives in
            # shift_work_windows (see migration 0011).
            work_start_time=windows[0][0] if windows else None,
            work_end_time=windows[-1][1] if windows else None,
        )
        db.add(day)
        db.flush()
        for order, (start, end) in enumerate(windows):
            db.add(
                ShiftWorkWindow(
                    shift_schedule_day_id=day.id,
                    work_start_time=start,
                    work_end_time=end,
                    sort_order=order,
                )
            )
        for bw_in in day_in.break_windows:
            db.add(
                ShiftBreakWindow(
                    shift_schedule_day_id=day.id,
                    break_start_time=bw_in.break_start_time,
                    break_end_time=bw_in.break_end_time,
                    is_paid=bw_in.is_paid,
                )
            )
        created_days.append(day)
    db.commit()
    for day in created_days:
        db.refresh(day)
    return created_days
