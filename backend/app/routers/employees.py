"""Employees & enrollments — BLUEPRINT.md Section 4.4.

GAP RESOLUTION (FRONTEND_NOTES.md #4 — manager employee-filter scoping):
BLUEPRINT.md Section 4.4 scoped `GET /employees` to role `A` only, but
DESIGN_SPEC.md requires a searchable Employee Select on Attendance/Leave
pages that must work for Managers too, and BLUEPRINT.md Section 6.2 already
establishes the general principle that "every list/detail endpoint scoped to
a manager filters at the query level." Resolution chosen: option (a) from
FRONTEND_NOTES.md — `GET /employees` and `GET /employees/{id}` are relaxed to
allow role `M`, with the list/detail results filtered server-side to
`employees.location_id = current_user.location_id` (location-based scoping,
2026-08-22 access-control change — see BLUEPRINT.md Section 6.2). Write
endpoints (POST/PUT, enrollments, shift-assignments) remain `A`-only per
BLUEPRINT.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import false
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_location_access, get_current_user, require_admin, require_manager_or_admin
from app.models import (
    Device,
    Employee,
    EmployeeDeviceEnrollment,
    EmployeeShiftAssignment,
    Location,
    ShiftScheduleDay,
    User,
)
from app.pagination import paginate
from app.schemas import (
    BulkImportResult,
    EmployeeCreate,
    EmployeeDeviceEnrollmentCreate,
    EmployeeDeviceEnrollmentOut,
    EmployeeOut,
    EmployeeShiftAssignmentCreate,
    EmployeeShiftAssignmentOut,
    EmployeeShiftAssignmentUpdate,
    EmployeeUpdate,
    Paginated,
)
from app.services.bulk_import import run_csv_bulk_import

router = APIRouter(prefix="/employees", tags=["employees"])


def _serialize(emp: Employee) -> EmployeeOut:
    out = EmployeeOut.model_validate(emp)
    out.location_name = emp.location.name if emp.location else None
    out.manager_name = f"{emp.manager.employee.first_name} {emp.manager.employee.last_name}" if (
        emp.manager and emp.manager.employee
    ) else (emp.manager.username if emp.manager else None)
    return out


def _get_employee_or_404(db: Session, employee_id: int) -> Employee:
    emp = db.get(Employee, employee_id)
    if emp is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return emp


def _assert_manager_can_view(emp: Employee, user: User) -> None:
    # Location-based scoping (BLUEPRINT.md Section 6.2/6.3, 2026-08-22
    # access-control change) — replaces the old manager_user_id direct-report
    # check. A manager with no assigned location (user.location_id is None)
    # explicitly matches nothing, fail-closed.
    if user.role == "manager" and (user.location_id is None or emp.location_id != user.location_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your location")


@router.get("", response_model=Paginated[EmployeeOut])
def list_employees(
    location_id: int | None = None,
    status_: str | None = Query(default=None, alias="status"),
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Employee)
    if user.role == "manager":
        # Location-based scoping (BLUEPRINT.md Section 6.2/6.3). A manager
        # with no assigned location matches nothing, fail-closed.
        if user.location_id is None:
            q = q.filter(false())
        else:
            q = q.filter(Employee.location_id == user.location_id)
    if location_id is not None:
        q = q.filter(Employee.location_id == location_id)
    if status_ is not None:
        q = q.filter(Employee.employment_status == status_)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (Employee.first_name.ilike(like))
            | (Employee.last_name.ilike(like))
            | (Employee.employee_code.ilike(like))
        )
    q = q.order_by(Employee.last_name, Employee.first_name)
    return paginate(db, q, page, page_size, serialize=_serialize)


@router.post("", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_manager_or_admin)])
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_location_access(user, payload.location_id)
    if db.get(Location, payload.location_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not found")
    if db.query(Employee).filter(Employee.employee_code == payload.employee_code).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee code must be unique")
    emp = Employee(**payload.model_dump())
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _serialize(emp)


@router.post(
    "/bulk-import",
    response_model=BulkImportResult,
    dependencies=[Depends(require_admin)],
)
async def bulk_import_employees(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Accepts .csv or .xlsx. Columns: location_id, employee_code, first_name, last_name,
    national_id (optional), job_title (optional), hire_date (YYYY-MM-DD),
    base_salary_eur, manager_user_id (optional), employment_status
    (optional, default active)."""

    def insert(db: Session, payload: EmployeeCreate) -> None:
        if db.get(Location, payload.location_id) is None:
            raise ValueError("Location not found")
        if db.query(Employee).filter(Employee.employee_code == payload.employee_code).first():
            raise ValueError("Employee code must be unique")
        if payload.manager_user_id is not None and db.get(User, payload.manager_user_id) is None:
            raise ValueError("Manager not found")
        db.add(Employee(**payload.model_dump()))
        db.flush()

    return await run_csv_bulk_import(db, file, EmployeeCreate, insert)


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    return _serialize(emp)


@router.put("/{employee_id}", response_model=EmployeeOut, dependencies=[Depends(require_manager_or_admin)])
def update_employee(employee_id: int, payload: EmployeeUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    assert_location_access(user, emp.location_id)
    data = payload.model_dump(exclude_unset=True)
    if "location_id" in data:
        assert_location_access(user, data["location_id"])
    if "employee_code" in data and data["employee_code"] != emp.employee_code:
        if db.query(Employee).filter(Employee.employee_code == data["employee_code"]).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee code must be unique")
    for k, v in data.items():
        setattr(emp, k, v)
    db.commit()
    db.refresh(emp)
    return _serialize(emp)


# ---- Device enrollments ----


@router.get(
    "/{employee_id}/device-enrollments",
    response_model=list[EmployeeDeviceEnrollmentOut],
    dependencies=[Depends(require_manager_or_admin)],
)
def list_enrollments(employee_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    rows = db.query(EmployeeDeviceEnrollment).filter(EmployeeDeviceEnrollment.employee_id == employee_id).all()
    out = []
    for r in rows:
        item = EmployeeDeviceEnrollmentOut.model_validate(r)
        item.device_label = r.device.label if r.device else None
        out.append(item)
    return out


@router.post(
    "/{employee_id}/device-enrollments",
    response_model=EmployeeDeviceEnrollmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_manager_or_admin)],
)
def create_enrollment(employee_id: int, payload: EmployeeDeviceEnrollmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    # SECURITY (SECURITY_REPORT.md Revision 3): the device has its own
    # location and was never checked here — a manager could bind one of their
    # own employees to another location's reader (and, via the 201 body, read
    # back that device's label). It also 500'd on a non-existent device_id
    # because the FK violation was never pre-validated.
    device = db.get(Device, payload.device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Device not found")
    assert_location_access(user, device.location_id)
    existing = (
        db.query(EmployeeDeviceEnrollment)
        .filter(
            EmployeeDeviceEnrollment.device_id == payload.device_id,
            EmployeeDeviceEnrollment.device_user_id == payload.device_user_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This device_user_id is already enrolled on this device",
        )
    from datetime import datetime, timezone

    enrollment = EmployeeDeviceEnrollment(
        employee_id=employee_id,
        device_id=payload.device_id,
        device_user_id=payload.device_user_id,
        enrolled_at=datetime.now(timezone.utc),
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    out = EmployeeDeviceEnrollmentOut.model_validate(enrollment)
    out.device_label = enrollment.device.label if enrollment.device else None
    return out


@router.delete(
    "/{employee_id}/device-enrollments/{enrollment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_manager_or_admin)],
)
def delete_enrollment(employee_id: int, enrollment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    row = db.get(EmployeeDeviceEnrollment, enrollment_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Enrollment not found")
    db.delete(row)
    db.commit()


# ---- Shift assignments ----


@router.get(
    "/{employee_id}/shift-assignments",
    response_model=list[EmployeeShiftAssignmentOut],
    dependencies=[Depends(require_manager_or_admin)],
)
def list_shift_assignments(employee_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    rows = (
        db.query(EmployeeShiftAssignment)
        .filter(EmployeeShiftAssignment.employee_id == employee_id)
        .order_by(EmployeeShiftAssignment.effective_from.desc())
        .all()
    )
    out = []
    for r in rows:
        item = EmployeeShiftAssignmentOut.model_validate(r)
        item.shift_schedule_name = r.shift_schedule.name if r.shift_schedule else None
        out.append(item)
    return out


def _working_days(db: Session, shift_schedule_id: int) -> set[int]:
    rows = (
        db.query(ShiftScheduleDay.day_of_week)
        .filter(
            ShiftScheduleDay.shift_schedule_id == shift_schedule_id,
            ShiftScheduleDay.is_working_day.is_(True),
        )
        .all()
    )
    return {row[0] for row in rows}


def _assert_no_conflict(
    db: Session, employee_id: int, shift_schedule_id: int, effective_from, effective_to, exclude_id: int | None = None
):
    """App-layer invariant, relaxed 2026-09-17 from BLUEPRINT.md Section 3.6's
    original "no overlapping date ranges at all".

    An employee may now hold several assignments covering the same dates, so
    long as the schedules behind them claim different weekdays — that is how
    "Cafe Shift on Mon-Tue, Office Shift on Wed-Fri" is expressed, both
    open-ended. What stays forbidden is two assignments claiming the SAME
    weekday over the same dates, because then no rule could say which one a
    Monday belongs to (see services/shift_lookup.py).
    """
    new_days = _working_days(db, shift_schedule_id)
    q = db.query(EmployeeShiftAssignment).filter(EmployeeShiftAssignment.employee_id == employee_id)
    if exclude_id is not None:
        q = q.filter(EmployeeShiftAssignment.id != exclude_id)
    for existing in q.all():
        existing_end = existing.effective_to
        new_end = effective_to
        starts_before_existing_ends = existing_end is None or effective_from < existing_end
        existing_starts_before_new_ends = new_end is None or existing.effective_from < new_end
        if not (starts_before_existing_ends and existing_starts_before_new_ends):
            continue
        clash = new_days & _working_days(db, existing.shift_schedule_id)
        if clash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This employee already has a shift covering the same days in that date range. "
                    "Two schedules can overlap in dates only if they work different days of the week."
                ),
            )


@router.post(
    "/{employee_id}/shift-assignments",
    response_model=EmployeeShiftAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_manager_or_admin)],
)
def create_shift_assignment(employee_id: int, payload: EmployeeShiftAssignmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    _assert_no_conflict(
        db, employee_id, payload.shift_schedule_id, payload.effective_from, payload.effective_to
    )
    row = EmployeeShiftAssignment(employee_id=employee_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    out = EmployeeShiftAssignmentOut.model_validate(row)
    out.shift_schedule_name = row.shift_schedule.name if row.shift_schedule else None
    return out


@router.put(
    "/{employee_id}/shift-assignments/{assignment_id}",
    response_model=EmployeeShiftAssignmentOut,
    dependencies=[Depends(require_manager_or_admin)],
)
def update_shift_assignment(
    employee_id: int,
    assignment_id: int,
    payload: EmployeeShiftAssignmentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    row = db.get(EmployeeShiftAssignment, assignment_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift assignment not found")
    data = payload.model_dump(exclude_unset=True)
    new_from = data.get("effective_from", row.effective_from)
    new_to = data.get("effective_to", row.effective_to)
    new_schedule_id = data.get("shift_schedule_id", row.shift_schedule_id)
    _assert_no_conflict(db, employee_id, new_schedule_id, new_from, new_to, exclude_id=assignment_id)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    out = EmployeeShiftAssignmentOut.model_validate(row)
    out.shift_schedule_name = row.shift_schedule.name if row.shift_schedule else None
    return out


@router.delete(
    "/{employee_id}/shift-assignments/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_manager_or_admin)],
)
def delete_shift_assignment(employee_id: int, assignment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    emp = _get_employee_or_404(db, employee_id)
    _assert_manager_can_view(emp, user)
    row = db.get(EmployeeShiftAssignment, assignment_id)
    if row is None or row.employee_id != employee_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shift assignment not found")
    db.delete(row)
    db.commit()
