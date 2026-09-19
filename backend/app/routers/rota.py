"""Shift templates and the per-date rota.

A shift template is a named, reusable shift ("Paradite 10:00-18:00, 30min
break"). The rota assigns a template to an employee for a specific date; a
NULL template is an explicit day off. A rota entry overrides the weekly
schedule for its date (services/shift_lookup.resolve_day).

`GET /rota` returns a week's grid for a location; `PUT /rota` sets or clears
entries in bulk (one save for a whole week of edits). Changing the rota does
not recompute on its own — the caller re-runs /attendance/recompute for the
affected dates, the same rule the weekly schedule follows.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import false, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_location_access, get_current_user, require_manager_or_admin
from app.models import Employee, RosterEntry, ShiftTemplate, User
from app.schemas import (
    RosterOut,
    RosterReplace,
    ShiftTemplateCreate,
    ShiftTemplateOut,
    ShiftTemplateUpdate,
)

router = APIRouter(tags=["rota"], dependencies=[Depends(require_manager_or_admin)])


# ---- Shift templates ------------------------------------------------------

def _serialize_template(t: ShiftTemplate) -> ShiftTemplateOut:
    out = ShiftTemplateOut.model_validate(t)
    out.location_name = t.location.name if t.location else None
    return out


def _validate_template(payload) -> None:
    if payload.work_end_time <= payload.work_start_time:
        raise HTTPException(status_code=400, detail="Work must end after it starts")
    if bool(payload.break_start_time) != bool(payload.break_end_time):
        raise HTTPException(status_code=400, detail="A break needs both a start and an end time")
    if payload.break_start_time and payload.break_end_time <= payload.break_start_time:
        raise HTTPException(status_code=400, detail="Break must end after it starts")


@router.get("/shift-templates", response_model=list[ShiftTemplateOut])
def list_templates(location_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(ShiftTemplate)
    if user.role == "manager":
        q = q.filter(or_(ShiftTemplate.location_id == user.location_id, ShiftTemplate.location_id.is_(None)))
    if location_id is not None:
        q = q.filter(or_(ShiftTemplate.location_id == location_id, ShiftTemplate.location_id.is_(None)))
    return [_serialize_template(t) for t in q.order_by(ShiftTemplate.work_start_time, ShiftTemplate.name).all()]


@router.post("/shift-templates", response_model=ShiftTemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(payload: ShiftTemplateCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_location_access(user, payload.location_id)
    _validate_template(payload)
    t = ShiftTemplate(**payload.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return _serialize_template(t)


@router.put("/shift-templates/{template_id}", response_model=ShiftTemplateOut)
def update_template(template_id: int, payload: ShiftTemplateUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(ShiftTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Shift template not found")
    assert_location_access(user, t.location_id)
    data = payload.model_dump(exclude_unset=True)
    if "location_id" in data:
        assert_location_access(user, data["location_id"])
    for k, v in data.items():
        setattr(t, k, v)
    _validate_template(t)
    db.commit()
    db.refresh(t)
    return _serialize_template(t)


@router.delete("/shift-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    t = db.get(ShiftTemplate, template_id)
    if t is None:
        raise HTTPException(status_code=404, detail="Shift template not found")
    assert_location_access(user, t.location_id)
    # A template in use by roster entries must not vanish under them; deactivate
    # instead so history stays intact.
    in_use = db.query(RosterEntry).filter(RosterEntry.shift_template_id == template_id).first()
    if in_use is not None:
        raise HTTPException(status_code=409, detail="This shift is used in the rota; deactivate it instead of deleting")
    db.delete(t)
    db.commit()


# ---- Rota -----------------------------------------------------------------

def _employees_at(db: Session, location_id: int, user: User):
    if user.role == "manager" and user.location_id != location_id:
        return []
    return (
        db.query(Employee)
        .filter(Employee.location_id == location_id, Employee.employment_status == "active")
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )


@router.get("/rota", response_model=RosterOut)
def get_rota(
    location_id: int,
    week_start: date,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One week (7 days from week_start) for a location: each active employee
    with the shift assigned on each date, if any."""
    assert_location_access(user, location_id)
    dates = [week_start + timedelta(days=i) for i in range(7)]
    employees = _employees_at(db, location_id, user)
    emp_ids = [e.id for e in employees]

    entries = {}
    if emp_ids:
        rows = (
            db.query(RosterEntry)
            .filter(
                RosterEntry.employee_id.in_(emp_ids),
                RosterEntry.work_date >= dates[0],
                RosterEntry.work_date <= dates[-1],
            )
            .all()
        )
        for r in rows:
            entries[(r.employee_id, r.work_date.isoformat())] = r.shift_template_id

    return RosterOut(
        location_id=location_id,
        week_start=week_start,
        dates=[d.isoformat() for d in dates],
        employees=[
            {
                "employee_id": e.id,
                "employee_name": f"{e.first_name} {e.last_name}",
                "assignments": {d.isoformat(): entries.get((e.id, d.isoformat())) for d in dates},
            }
            for e in employees
        ],
    )


@router.put("/rota", status_code=status.HTTP_204_NO_CONTENT)
def set_rota(payload: RosterReplace, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Set or clear rota entries in bulk. Each item is (employee_id, date,
    shift_template_id | null-for-day-off | absent-to-remove-the-entry).

    An item with `clear: true` removes the entry (falls back to the weekly
    schedule); otherwise it upserts the entry to the given template (or a day
    off when template is null)."""
    for item in payload.entries:
        emp = db.get(Employee, item.employee_id)
        if emp is None:
            raise HTTPException(status_code=400, detail=f"Employee {item.employee_id} not found")
        assert_location_access(user, emp.location_id)
        if item.shift_template_id is not None:
            tmpl = db.get(ShiftTemplate, item.shift_template_id)
            if tmpl is None:
                raise HTTPException(status_code=400, detail=f"Shift template {item.shift_template_id} not found")

        existing = (
            db.query(RosterEntry)
            .filter(RosterEntry.employee_id == item.employee_id, RosterEntry.work_date == item.work_date)
            .first()
        )
        if item.clear:
            if existing is not None:
                db.delete(existing)
            continue
        if existing is not None:
            existing.shift_template_id = item.shift_template_id
        else:
            db.add(
                RosterEntry(
                    employee_id=item.employee_id,
                    work_date=item.work_date,
                    shift_template_id=item.shift_template_id,
                )
            )
    db.commit()
