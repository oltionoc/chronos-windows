from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import false
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_location_access, get_current_user, require_admin, require_manager_or_admin
from app.models import (
    AttendanceDailyStatus,
    AttendanceLog,
    Employee,
    EmployeeDeviceEnrollment,
    OvertimeConfig,
    User,
)
from app.pagination import paginate
from app.schemas import (
    AttendanceDailyStatusOut,
    AttendanceLogOut,
    AttendanceLogResolve,
    AttendanceRecomputeRequest,
    Paginated,
    SetExcusedRequest,
    SetOvertimeApprovalRequest,
)
from app.services.config_lookup import get_effective_config
from app.services.recompute import recompute_range

router = APIRouter(prefix="/attendance", tags=["attendance"])


def _serialize_log(log: AttendanceLog) -> AttendanceLogOut:
    out = AttendanceLogOut.model_validate(log)
    out.device_label = log.device.label if log.device else None
    out.employee_name = f"{log.employee.first_name} {log.employee.last_name}" if log.employee else None
    return out


def _status_serializer(db: Session):
    """Builds the daily-status serializer for one request.

    `overtime_requires_approval` comes from the overtime_config effective for
    that location/date, so the answer is per-row — but a listing page is
    almost always one location and a handful of dates, hence the small cache
    rather than a config lookup per row."""
    cache: dict[tuple[int | None, date], bool] = {}

    def serialize(row: AttendanceDailyStatus) -> AttendanceDailyStatusOut:
        out = AttendanceDailyStatusOut.model_validate(row)
        out.employee_name = f"{row.employee.first_name} {row.employee.last_name}" if row.employee else None
        if row.overtime_minutes:
            location_id = row.employee.location_id if row.employee else None
            key = (location_id, row.work_date)
            if key not in cache:
                cfg = get_effective_config(db, OvertimeConfig, location_id, row.work_date)
                cache[key] = bool(cfg is not None and cfg.requires_preapproval)
            out.overtime_requires_approval = cache[key]
        return out

    return serialize


@router.get("/logs", response_model=Paginated[AttendanceLogOut], dependencies=[Depends(require_admin)])
def list_logs(
    employee_id: int | None = None,
    device_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    unresolved_only: bool = False,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    q = db.query(AttendanceLog)
    if employee_id is not None:
        q = q.filter(AttendanceLog.employee_id == employee_id)
    if device_id is not None:
        q = q.filter(AttendanceLog.device_id == device_id)
    if date_from is not None:
        q = q.filter(AttendanceLog.punch_timestamp >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        q = q.filter(AttendanceLog.punch_timestamp <= datetime.combine(date_to, datetime.max.time()))
    if unresolved_only:
        q = q.filter(AttendanceLog.employee_id.is_(None))
    q = q.order_by(AttendanceLog.punch_timestamp.desc())
    return paginate(db, q, page, page_size, serialize=_serialize_log)


@router.patch("/logs/{log_id}/resolve", response_model=AttendanceLogOut, dependencies=[Depends(require_admin)])
def resolve_log(log_id: int, payload: AttendanceLogResolve, db: Session = Depends(get_db)):
    log = db.get(AttendanceLog, log_id)
    if log is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance log not found")
    employee = db.get(Employee, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee not found")

    log.employee_id = payload.employee_id

    existing_enrollment = (
        db.query(EmployeeDeviceEnrollment)
        .filter(
            EmployeeDeviceEnrollment.device_id == log.device_id,
            EmployeeDeviceEnrollment.device_user_id == log.device_user_id,
        )
        .first()
    )
    if existing_enrollment is None:
        db.add(
            EmployeeDeviceEnrollment(
                employee_id=payload.employee_id,
                device_id=log.device_id,
                device_user_id=log.device_user_id,
                enrolled_at=datetime.utcnow(),
            )
        )
    db.commit()
    db.refresh(log)
    return _serialize_log(log)


@router.get("/daily-status", response_model=Paginated[AttendanceDailyStatusOut])
def list_daily_status(
    employee_id: int | None = None,
    location_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    status_: str | None = Query(default=None, alias="status"),
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(AttendanceDailyStatus).join(Employee, AttendanceDailyStatus.employee_id == Employee.id)
    if user.role == "manager":
        # Location-based scoping (BLUEPRINT.md Section 6.2/6.3). A manager
        # with no assigned location matches nothing, fail-closed.
        if user.location_id is None:
            q = q.filter(false())
        else:
            q = q.filter(Employee.location_id == user.location_id)
    if employee_id is not None:
        q = q.filter(AttendanceDailyStatus.employee_id == employee_id)
    if location_id is not None:
        q = q.filter(Employee.location_id == location_id)
    if date_from is not None:
        q = q.filter(AttendanceDailyStatus.work_date >= date_from)
    if date_to is not None:
        q = q.filter(AttendanceDailyStatus.work_date <= date_to)
    if status_ is not None:
        # Comma-separated multi-status filter — the frontend's status
        # multi-select already sends e.g. "present,late" (see
        # AttendanceDailyStatusPage.tsx), and the Dashboard's "Present" card
        # drills into both present+late since that KPI counts late arrivals
        # as present too. A single value works the same as before.
        statuses = [s for s in status_.split(",") if s]
        q = q.filter(AttendanceDailyStatus.status.in_(statuses))
    q = q.order_by(AttendanceDailyStatus.work_date.desc())
    return paginate(db, q, page, page_size, serialize=_status_serializer(db))


@router.post("/recompute", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def trigger_recompute(payload: AttendanceRecomputeRequest, db: Session = Depends(get_db)):
    recompute_range(db, payload.date_from, payload.date_to, payload.employee_id)


@router.patch("/daily-status/{daily_status_id}/excused", response_model=AttendanceDailyStatusOut, dependencies=[Depends(require_admin)])
def set_excused(daily_status_id: int, payload: SetExcusedRequest, db: Session = Depends(get_db)):
    """ASSUMED endpoint per FRONTEND_NOTES.md #1 — BLUEPRINT.md Section 4.6
    does not list a write route for `is_absence_excused`, but the daily
    status table requires inline HR toggling. Implemented exactly at the
    path/verb the frontend already calls."""
    row = db.get(AttendanceDailyStatus, daily_status_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily status row not found")
    row.is_absence_excused = payload.is_absence_excused
    db.commit()
    db.refresh(row)
    return _status_serializer(db)(row)


@router.patch(
    "/daily-status/{daily_status_id}/overtime-approval",
    response_model=AttendanceDailyStatusOut,
    dependencies=[Depends(require_manager_or_admin)],
)
def set_overtime_approval(
    daily_status_id: int,
    payload: SetOvertimeApprovalRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Approve (or withdraw approval for) one day's overtime.

    Only matters when the effective overtime_config has
    `requires_preapproval` set — with the flag off, overtime pays either way
    and this is a no-op record. Approval is tied to the minute count that was
    approved: services/recompute.py clears it if a later punch changes that
    number."""
    row = db.get(AttendanceDailyStatus, daily_status_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily status row not found")
    employee = db.get(Employee, row.employee_id)
    assert_location_access(user, employee.location_id if employee else None)

    if payload.approved:
        row.overtime_approved_at = datetime.now(timezone.utc)
        row.overtime_approved_by_user_id = user.id
    else:
        row.overtime_approved_at = None
        row.overtime_approved_by_user_id = None
    db.commit()
    db.refresh(row)
    return _status_serializer(db)(row)
