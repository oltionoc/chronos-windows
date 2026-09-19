import calendar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import false, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_location_access, require_manager_or_admin
from app.models import (
    AttendanceDailyStatus,
    Employee,
    PayrollAdjustment,
    PayrollRun,
    PayrollRunLine,
    User,
)
from app.schemas import (
    PayrollAdjustmentCreate,
    PayrollAdjustmentOut,
    PayrollRunCreate,
    PayrollRunLineDetailOut,
    PayrollRunLineOut,
    PayrollRunOut,
)
from app.services.excel import generate_payroll_run_xlsx, generate_payslip_xlsx
from app.services.payroll_calc import create_payroll_run, recalculate_line_net_pay

router = APIRouter(prefix="/payroll", tags=["payroll"], dependencies=[Depends(require_manager_or_admin)])


def _serialize_run(run: PayrollRun, db: Session) -> PayrollRunOut:
    out = PayrollRunOut.model_validate(run)
    out.location_name = run.location.name if run.location else None
    out.generated_by_name = run.generated_by.username if run.generated_by else None
    agg = (
        db.query(func.count(PayrollRunLine.id), func.coalesce(func.sum(PayrollRunLine.net_pay_eur), 0))
        .filter(PayrollRunLine.payroll_run_id == run.id)
        .first()
    )
    out.line_count = agg[0] or 0
    out.total_net_pay_eur = float(agg[1] or 0)
    return out


def _serialize_line(line: PayrollRunLine) -> PayrollRunLineOut:
    out = PayrollRunLineOut.model_validate(line)
    out.employee_name = f"{line.employee.first_name} {line.employee.last_name}" if line.employee else None
    return out


def _get_run_or_404(db: Session, run_id: int) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    return run


@router.get("/runs", response_model=list[PayrollRunOut])
def list_runs(
    location_id: int | None = None,
    year: int | None = None,
    status_: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager_or_admin),
):
    q = db.query(PayrollRun)
    if user.role == "manager":
        # Fail closed for a manager with no assigned location — `== None`
        # compiles to `IS NULL`, which would have matched every org-wide
        # payroll run instead of nothing (SECURITY_REPORT.md Revision 3).
        # Matches the `false()` pattern used in employees.py/attendance.py.
        if user.location_id is None:
            q = q.filter(false())
        else:
            q = q.filter(PayrollRun.location_id == user.location_id)
    if location_id is not None:
        q = q.filter(PayrollRun.location_id == location_id)
    if year is not None:
        q = q.filter(PayrollRun.period_year == year)
    if status_ is not None:
        q = q.filter(PayrollRun.status == status_)
    q = q.order_by(PayrollRun.period_year.desc(), PayrollRun.period_month.desc())
    return [_serialize_run(r, db) for r in q.all()]


@router.post("/runs", response_model=PayrollRunOut, status_code=status.HTTP_201_CREATED)
def create_run(payload: PayrollRunCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    assert_location_access(user, payload.location_id)
    existing = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.location_id == payload.location_id,
            PayrollRun.period_year == payload.period_year,
            PayrollRun.period_month == payload.period_month,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A payroll run already exists for this location and period",
        )
    run = create_payroll_run(db, payload.period_year, payload.period_month, payload.location_id, user.id)
    db.commit()
    db.refresh(run)
    return _serialize_run(run, db)


@router.get("/runs/{run_id}", response_model=PayrollRunOut)
def get_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    return _serialize_run(run, db)


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    if run.status == "finalized":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete a finalized payroll run")
    db.delete(run)
    db.commit()


@router.get("/runs/{run_id}/lines", response_model=list[PayrollRunLineOut])
def list_lines(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    lines = db.query(PayrollRunLine).filter(PayrollRunLine.payroll_run_id == run_id).all()
    return [_serialize_line(l) for l in lines]


@router.get("/runs/{run_id}/export.xlsx")
def export_run_xlsx(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    lines = db.query(PayrollRunLine).filter(PayrollRunLine.payroll_run_id == run_id).all()
    content = generate_payroll_run_xlsx(run, lines)
    filename = f"payroll_{run.period_year}-{run.period_month:02d}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _get_line(db: Session, run_id: int, employee_id: int) -> PayrollRunLine:
    line = (
        db.query(PayrollRunLine)
        .filter(PayrollRunLine.payroll_run_id == run_id, PayrollRunLine.employee_id == employee_id)
        .first()
    )
    if line is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run line not found")
    return line


@router.get("/runs/{run_id}/lines/{employee_id}", response_model=PayrollRunLineDetailOut)
def get_line_detail(run_id: int, employee_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    line = _get_line(db, run_id, employee_id)
    out = PayrollRunLineDetailOut.model_validate(line)
    out.employee_name = f"{line.employee.first_name} {line.employee.last_name}" if line.employee else None
    out.adjustments = [
        _serialize_adjustment(a) for a in line.adjustments
    ]
    return out


def _serialize_adjustment(a: PayrollAdjustment) -> PayrollAdjustmentOut:
    out = PayrollAdjustmentOut.model_validate(a)
    out.created_by_name = a.created_by.username if a.created_by else None
    return out


@router.post("/runs/{run_id}/lines/{employee_id}/adjustments", response_model=PayrollAdjustmentOut, status_code=status.HTTP_201_CREATED)
def add_adjustment(
    run_id: int, employee_id: int, payload: PayrollAdjustmentCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)
):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    if run.status == "finalized":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot modify a finalized payroll run")
    line = _get_line(db, run_id, employee_id)

    adjustment = PayrollAdjustment(
        payroll_run_line_id=line.id,
        type=payload.type,
        amount_eur=payload.amount_eur,
        reason=payload.reason,
        created_by_user_id=user.id,
    )
    db.add(adjustment)
    db.flush()
    recalculate_line_net_pay(db, line)
    db.commit()
    db.refresh(adjustment)
    return _serialize_adjustment(adjustment)


@router.post("/runs/{run_id}/finalize", response_model=PayrollRunOut)
def finalize_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    if run.status == "finalized":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payroll run is already finalized")

    run.status = "finalized"
    run.finalized_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(run)
    return _serialize_run(run, db)


def _daily_breakdown_rows(db: Session, run: PayrollRun, employee_id: int) -> list[list]:
    """One row per calendar day of the run's month for this employee: the
    scheduled window, the actual in/out (in the location's timezone), and the
    lateness/break/overtime that fed the monthly totals. Days with no computed
    status (e.g. before hire) show blanks."""
    tz = ZoneInfo(run.location.timezone) if run.location and run.location.timezone else timezone.utc
    days_in_month = calendar.monthrange(run.period_year, run.period_month)[1]
    first = date(run.period_year, run.period_month, 1)
    last = date(run.period_year, run.period_month, days_in_month)

    statuses = {
        s.work_date: s
        for s in db.query(AttendanceDailyStatus)
        .filter(
            AttendanceDailyStatus.employee_id == employee_id,
            AttendanceDailyStatus.work_date >= first,
            AttendanceDailyStatus.work_date <= last,
        )
        .all()
    }

    def _t(dt: datetime | None) -> str:
        return dt.astimezone(tz).strftime("%H:%M") if dt else ""

    def _sched(s: AttendanceDailyStatus) -> str:
        if s.scheduled_start and s.scheduled_end:
            return f"{s.scheduled_start.strftime('%H:%M')}-{s.scheduled_end.strftime('%H:%M')}"
        return ""

    rows: list[list] = []
    for day_num in range(1, days_in_month + 1):
        d = date(run.period_year, run.period_month, day_num)
        s = statuses.get(d)
        if s is None:
            rows.append([d.isoformat(), "", "", "", "", "", "", "", "", ""])
            continue
        rows.append([
            d.isoformat(),
            s.status,
            _sched(s),
            _t(s.actual_first_in),
            _t(s.actual_last_out),
            s.late_minutes,
            s.early_departure_minutes,
            s.break_minutes_taken,
            s.overtime_minutes,
            s.penalty_occurrences,
        ])
    return rows


@router.get("/runs/{run_id}/lines/{employee_id}/payslip.xlsx")
def export_payslip_xlsx(run_id: int, employee_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    run = _get_run_or_404(db, run_id)
    assert_location_access(user, run.location_id)
    if run.status != "finalized":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payslip is only available once the run is finalized")
    line = _get_line(db, run_id, employee_id)
    emp = line.employee
    daily_rows = _daily_breakdown_rows(db, run, employee_id)
    content = generate_payslip_xlsx(line, line.adjustments, daily_rows)
    filename = f"payslip_{emp.employee_code}_{run.period_year}-{run.period_month:02d}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
