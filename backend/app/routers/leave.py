from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import false
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_location_access, get_current_user, require_admin, require_manager_or_admin
from app.models import Employee, LeaveRecord, LeaveType, User
from app.pagination import paginate
from app.schemas import (
    BulkImportResult,
    LeaveActionRequest,
    LeaveRecordCreate,
    LeaveRecordOut,
    LeaveTypeCreate,
    LeaveTypeOut,
    LeaveTypeUpdate,
    Paginated,
)
from app.services.bulk_import import run_csv_bulk_import
from app.services.recompute import recompute_range

router = APIRouter(tags=["leave"])


def _serialize(rec: LeaveRecord) -> LeaveRecordOut:
    out = LeaveRecordOut.model_validate(rec)
    out.employee_name = f"{rec.employee.first_name} {rec.employee.last_name}" if rec.employee else None
    out.leave_type_name_en = rec.leave_type.name_en if rec.leave_type else None
    out.leave_type_name_sq = rec.leave_type.name_sq if rec.leave_type else None
    out.requested_by_name = rec.requested_by.username if rec.requested_by else None
    out.approved_by_name = rec.approved_by.username if rec.approved_by else None
    return out


def _assert_manager_can_view(rec: LeaveRecord, user: User) -> None:
    # Location-based scoping (BLUEPRINT.md Section 6.2/6.3, 2026-08-22
    # access-control change). A manager with no assigned location
    # (user.location_id is None) explicitly matches nothing, fail-closed.
    if user.role == "manager" and (user.location_id is None or rec.employee.location_id != user.location_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your location")


# ---- Leave types (4.7) ----


@router.get("/leave-types", response_model=list[LeaveTypeOut])
def list_leave_types(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.query(LeaveType).order_by(LeaveType.name_en).all()


@router.post("/leave-types", response_model=LeaveTypeOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_leave_type(payload: LeaveTypeCreate, db: Session = Depends(get_db)):
    lt = LeaveType(**payload.model_dump())
    db.add(lt)
    db.commit()
    db.refresh(lt)
    return lt


@router.put("/leave-types/{leave_type_id}", response_model=LeaveTypeOut, dependencies=[Depends(require_admin)])
def update_leave_type(leave_type_id: int, payload: LeaveTypeUpdate, db: Session = Depends(get_db)):
    lt = db.get(LeaveType, leave_type_id)
    if lt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave type not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(lt, k, v)
    db.commit()
    db.refresh(lt)
    return lt


# ---- Leave records ----


@router.get("/leave-records", response_model=Paginated[LeaveRecordOut])
def list_leave_records(
    employee_id: int | None = None,
    location_id: int | None = None,
    status_: str | None = Query(default=None, alias="status"),
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(LeaveRecord).join(Employee, LeaveRecord.employee_id == Employee.id)
    if user.role == "manager":
        # Location-based scoping (BLUEPRINT.md Section 6.2/6.3). A manager
        # with no assigned location matches nothing, fail-closed.
        if user.location_id is None:
            q = q.filter(false())
        else:
            q = q.filter(Employee.location_id == user.location_id)
    if employee_id is not None:
        q = q.filter(LeaveRecord.employee_id == employee_id)
    if location_id is not None:
        q = q.filter(Employee.location_id == location_id)
    if status_ is not None:
        q = q.filter(LeaveRecord.status == status_)
    if date_from is not None:
        q = q.filter(LeaveRecord.end_date >= date_from)
    if date_to is not None:
        q = q.filter(LeaveRecord.start_date <= date_to)
    q = q.order_by(LeaveRecord.start_date.desc())
    return paginate(db, q, page, page_size, serialize=_serialize)


@router.get("/leave-records/{leave_id}", response_model=LeaveRecordOut)
def get_leave_record(leave_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ASSUMED endpoint per FRONTEND_NOTES.md #2 — not explicitly listed in
    BLUEPRINT.md Section 4.7 but required for the /leave/:id detail page."""
    rec = db.get(LeaveRecord, leave_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave record not found")
    _assert_manager_can_view(rec, user)
    return _serialize(rec)


@router.post("/leave-records", response_model=LeaveRecordOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_manager_or_admin)])
def create_leave_record(payload: LeaveRecordCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    employee = db.get(Employee, payload.employee_id)
    if employee is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Employee not found")
    assert_location_access(user, employee.location_id)
    leave_type = db.get(LeaveType, payload.leave_type_id)
    if leave_type is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Leave type not found")
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End date must be on or after start date")
    # Partial (hourly) leave: both times set, single day, end after start.
    if (payload.start_time is None) != (payload.end_time is None):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A partial leave needs both a start and an end time")
    if payload.start_time is not None:
        if payload.start_date != payload.end_date:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="An hourly leave must be on a single day")
        if payload.end_time <= payload.start_time:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The leave must end after it starts")

    # LeaveType.requires_approval was previously configurable but unused —
    # a "false" leave type still landed as "pending" forever. Now honored:
    # skip the approval step and record straight to "approved" so attendance
    # recompute picks it up immediately.
    auto_approved = not leave_type.requires_approval
    rec = LeaveRecord(
        employee_id=payload.employee_id,
        leave_type_id=payload.leave_type_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        start_time=payload.start_time,
        end_time=payload.end_time,
        notes=payload.notes,
        requested_by_user_id=user.id,
        status="approved" if auto_approved else "pending",
        approved_by_user_id=user.id if auto_approved else None,
        approved_at=datetime.now(timezone.utc) if auto_approved else None,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    if auto_approved:
        recompute_range(db, rec.start_date, rec.end_date, rec.employee_id)

    return _serialize(rec)


@router.post(
    "/leave-records/bulk-import",
    response_model=BulkImportResult,
    dependencies=[Depends(require_admin)],
)
async def bulk_import_leave_records(
    file: UploadFile = File(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Accepts .csv or .xlsx. Columns: employee_id, leave_type_id, start_date (YYYY-MM-DD),
    end_date (YYYY-MM-DD), notes (optional). Imported rows land as 'pending' —
    or straight to 'approved' if the leave type's requires_approval is false —
    same as a manually created leave record."""

    approved_ranges: list[tuple[date, date, int]] = []

    def insert(db: Session, payload: LeaveRecordCreate) -> None:
        if db.get(Employee, payload.employee_id) is None:
            raise ValueError("Employee not found")
        leave_type = db.get(LeaveType, payload.leave_type_id)
        if leave_type is None:
            raise ValueError("Leave type not found")
        if payload.end_date < payload.start_date:
            raise ValueError("End date must be on or after start date")
        auto_approved = not leave_type.requires_approval
        db.add(
            LeaveRecord(
                employee_id=payload.employee_id,
                leave_type_id=payload.leave_type_id,
                start_date=payload.start_date,
                end_date=payload.end_date,
                notes=payload.notes,
                requested_by_user_id=user.id,
                status="approved" if auto_approved else "pending",
                approved_by_user_id=user.id if auto_approved else None,
                approved_at=datetime.now(timezone.utc) if auto_approved else None,
            )
        )
        db.flush()
        if auto_approved:
            approved_ranges.append((payload.start_date, payload.end_date, payload.employee_id))

    result = await run_csv_bulk_import(db, file, LeaveRecordCreate, insert)
    for start_date, end_date, employee_id in approved_ranges:
        recompute_range(db, start_date, end_date, employee_id)
    return result


def _approve_reject(leave_id: int, new_status: str, payload: LeaveActionRequest, db: Session, user: User) -> LeaveRecordOut:
    rec = db.get(LeaveRecord, leave_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave record not found")
    # Location-based scoping (BLUEPRINT.md Section 6.2/6.3, 2026-08-22
    # access-control change). A manager with no assigned location
    # (user.location_id is None) explicitly matches nothing, fail-closed.
    if user.role == "manager" and (user.location_id is None or rec.employee.location_id != user.location_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your location")
    if rec.status != "pending":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending leave requests can be actioned")

    rec.status = new_status
    rec.approved_by_user_id = user.id
    rec.approved_at = datetime.now(timezone.utc)
    if payload.notes:
        rec.notes = payload.notes
    db.commit()

    if new_status == "approved":
        # Feed daily processing per BLUEPRINT.md Section 5.4/6: retroactively
        # recompute the affected date range so on_leave status is reflected.
        recompute_range(db, rec.start_date, rec.end_date, rec.employee_id)

    db.refresh(rec)
    return _serialize(rec)


@router.patch("/leave-records/{leave_id}/approve", response_model=LeaveRecordOut)
def approve_leave(leave_id: int, payload: LeaveActionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _approve_reject(leave_id, "approved", payload, db, user)


@router.patch("/leave-records/{leave_id}/reject", response_model=LeaveRecordOut)
def reject_leave(leave_id: int, payload: LeaveActionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _approve_reject(leave_id, "rejected", payload, db, user)


@router.delete("/leave-records/{leave_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_leave_record(leave_id: int, db: Session = Depends(get_db)):
    rec = db.get(LeaveRecord, leave_id)
    if rec is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Leave record not found")
    # A no-approval-required leave type auto-approves on creation (see
    # create_leave_record), so "pending" never happens for it — allow
    # deleting its auto-approved records too. A manually admin-approved
    # record (requires_approval leave type) stays protected as before.
    auto_approved = rec.status == "approved" and not rec.leave_type.requires_approval
    if rec.status != "pending" and not auto_approved:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only pending leave requests can be deleted")
    start_date, end_date, employee_id = rec.start_date, rec.end_date, rec.employee_id
    db.delete(rec)
    db.commit()
    if auto_approved:
        recompute_range(db, start_date, end_date, employee_id)
