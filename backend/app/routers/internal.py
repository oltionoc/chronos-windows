"""Internal ingestion API — worker -> api only, BLUEPRINT.md Section 4.10.
Reachable only with header `X-Internal-Key` matching `INTERNAL_API_KEY`; not
mounted for `frontend` consumption (no CORS origin needs it, and there is no
cookie-based auth check here — shared-secret only, per BLUEPRINT.md Section 7
"Internal service auth").
"""
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import verify_internal_key
from app.models import AttendanceLog, Device, EmployeeDeviceEnrollment
from app.schemas import (
    DeviceHeartbeat,
    IngestPunchesRequest,
    IngestPunchesResult,
    InternalDeviceOut,
    InternalEnrollmentOut,
    ProcessDailyStatusRequest,
    ProcessDailyStatusResult,
)
from app.services.classify import classify_employee_date
from app.services.recompute import recompute_employee_date, recompute_range
from app.services.shift_lookup import get_employee_timezone

router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(verify_internal_key)])

# SECURITY (SECURITY_REPORT.md Revision 3): `punch_type_hint` bypasses
# services/classify.py's inference and is written straight onto the log that
# feeds payroll, so only vendors whose protocol actually self-classifies may
# assert one. ZKTeco reports a bare numeric status code and its adapter never
# sets a hint — accepting one for a zkteco device would mean an ingestion
# caller could dictate check-in/check-out for a device that cannot report it.
_SELF_CLASSIFYING_DEVICE_TYPES = {"hikvision", "hikvision_cloud"}


@router.get("/devices", response_model=list[InternalDeviceOut])
def list_active_devices(db: Session = Depends(get_db)):
    """ADDED beyond BLUEPRINT.md Section 4.10's explicit list — necessary for
    `worker`'s design constraint (Section 2.2: "worker never writes to
    PostgreSQL directly"). Worker has no DB access at all, so it cannot know
    which devices exist/are active without asking `api`. Returns active
    devices only, with connection info (ip_address/port/device_type/auth)
    worker needs to poll via the matching vendor adapter — see
    worker/worker/sync.py. Uses InternalDeviceOut (not the admin-facing
    DeviceOut) since worker needs auth_password and DeviceOut deliberately
    never exposes it."""
    rows = db.query(Device).filter(Device.is_active.is_(True)).all()
    out = []
    for r in rows:
        item = InternalDeviceOut.model_validate(r)
        item.location_name = r.location.name if r.location else None
        out.append(item)
    return out


@router.get("/devices/{device_id}/enrollments", response_model=list[InternalEnrollmentOut])
def list_device_enrollments(device_id: int, db: Session = Depends(get_db)):
    """ADDED for the device-simulator service — not a real device need (a
    real K40 already knows its own enrolled fingerprints), but the simulator
    has to show a human which employee a `device_user_id` maps to, the same
    way it would show up on the physical unit's own screen."""
    rows = (
        db.query(EmployeeDeviceEnrollment)
        .filter(EmployeeDeviceEnrollment.device_id == device_id)
        .all()
    )
    return [
        InternalEnrollmentOut(
            employee_id=r.employee_id,
            employee_name=f"{r.employee.first_name} {r.employee.last_name}",
            device_user_id=r.device_user_id,
        )
        for r in rows
    ]


@router.post("/ingest/punches", response_model=IngestPunchesResult)
def ingest_punches(payload: IngestPunchesRequest, db: Session = Depends(get_db)):
    inserted = 0
    duplicates = 0
    unresolved = 0
    affected: set[tuple[int, date]] = set()

    device_types: dict[int, str | None] = {}

    for punch in payload.punches:
        if punch.punch_type_hint is not None:
            if punch.device_id not in device_types:
                device = db.get(Device, punch.device_id)
                device_types[punch.device_id] = device.device_type if device else None
            if device_types[punch.device_id] not in _SELF_CLASSIFYING_DEVICE_TYPES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Device {punch.device_id} does not self-classify punches; "
                        "punch_type_hint is not accepted for it"
                    ),
                )

        existing = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.device_id == punch.device_id,
                AttendanceLog.device_user_id == punch.device_user_id,
                AttendanceLog.punch_timestamp == punch.punch_timestamp,
                AttendanceLog.raw_status_code == punch.raw_status_code,
            )
            .first()
        )
        if existing is not None:
            duplicates += 1
            continue

        enrollment = (
            db.query(EmployeeDeviceEnrollment)
            .filter(
                EmployeeDeviceEnrollment.device_id == punch.device_id,
                EmployeeDeviceEnrollment.device_user_id == punch.device_user_id,
            )
            .first()
        )
        employee_id = enrollment.employee_id if enrollment else None
        if employee_id is None:
            unresolved += 1

        log = AttendanceLog(
            device_id=punch.device_id,
            device_user_id=punch.device_user_id,
            employee_id=employee_id,
            punch_timestamp=punch.punch_timestamp,
            raw_status_code=punch.raw_status_code,
            punch_type=None,
            punch_type_hint=punch.punch_type_hint,
            synced_at=datetime.now(timezone.utc),
        )
        db.add(log)
        db.flush()
        inserted += 1

        if employee_id is not None:
            tz = ZoneInfo(get_employee_timezone(db, employee_id))
            affected.add((employee_id, punch.punch_timestamp.astimezone(tz).date()))

    for employee_id, work_date in affected:
        classify_employee_date(db, employee_id, work_date)

    # Recompute daily status immediately for the affected (employee, date)
    # pairs, not just at the nightly batch — otherwise the dashboard's
    # present/late/absent counts stay blank for "today" until the nightly
    # job processes it as "yesterday" the following night. _compute() is
    # safe to call intraday: it derives present/late purely from whatever
    # punches exist so far (no check-out required).
    for employee_id, work_date in affected:
        recompute_employee_date(db, employee_id, work_date)

    db.commit()
    return IngestPunchesResult(inserted=inserted, duplicates=duplicates, unresolved=unresolved)


@router.post("/process/daily-status", response_model=ProcessDailyStatusResult)
def process_daily_status(payload: ProcessDailyStatusRequest, db: Session = Depends(get_db)):
    count = recompute_range(db, payload.work_date, payload.work_date, None)
    return ProcessDailyStatusResult(processed_employees=count)


@router.patch("/devices/{device_id}/heartbeat", status_code=204)
def device_heartbeat(
    device_id: int, payload: DeviceHeartbeat | None = None, db: Session = Depends(get_db)
):
    device = db.get(Device, device_id)
    if device is not None:
        now = datetime.now(timezone.utc)
        device.last_synced_at = now
        # A sync that could not read the clock (vendor has no endpoint, or the
        # read failed) leaves the previous reading and its timestamp alone
        # rather than overwriting a real measurement with "unknown" — the
        # alert ages the reading out on its own.
        if payload is not None and payload.clock_skew_seconds is not None:
            device.clock_skew_seconds = payload.clock_skew_seconds
            device.clock_checked_at = now
        db.commit()
