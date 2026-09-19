"""Pydantic schemas — mirrors frontend/src/api/types.ts exactly (field names,
nullability, shapes) since frontend is already built against that contract.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.services.device_net import validate_device_host

# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------

T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    total_pages: int


class BulkImportError(BaseModel):
    row: int
    message: str


class BulkImportResult(BaseModel):
    created: int
    errors: list[BulkImportError]


Role = Literal["admin", "manager"]


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    employee_id: int | None
    employee_name: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    is_active: bool
    last_login_at: datetime | None
    must_change_password: bool


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    # SECURITY: minimum length floor for a self-service password change —
    # see SECURITY_REPORT.md "no password strength/length validation".
    new_password: str = Field(min_length=8)


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    address: str | None
    timezone: str
    is_active: bool


class LocationCreate(BaseModel):
    name: str
    address: str | None = None
    timezone: str = "Europe/Tirane"
    is_active: bool = True


class LocationUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    timezone: str | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


DeviceType = Literal["zkteco", "hikvision", "hikvision_cloud"]

# SECURITY (SECURITY_REPORT.md Revision 3): `ip_address` is a free-text column
# since migration 0009 and is concatenated straight into the outbound URL the
# `api` test-connection endpoint and the `worker` Hikvision adapters build. A
# value like "host/path#" or "user:pass@host" rewrites that whole URL, so it
# is pinned to a bare IP/hostname here, at the only boundary it can enter
# through. Ports keep their own 1-65535 bound for the same reason.
DeviceHost = Annotated[str, AfterValidator(validate_device_host)]
DevicePort = Annotated[int, Field(ge=1, le=65535)]


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    location_name: str | None = None
    label: str
    ip_address: str
    port: int
    serial_number: str | None
    device_type: DeviceType
    # auth_username is shown (not secret); auth_password never round-trips
    # back to a client, same posture as user password hashes.
    auth_username: str | None = None
    is_active: bool
    last_synced_at: datetime | None
    # Device clock vs server clock, seconds ahead (negative = behind). NULL
    # means never measured, which is not the same as measured zero.
    clock_skew_seconds: int | None = None
    clock_checked_at: datetime | None = None


class DeviceHeartbeat(BaseModel):
    clock_skew_seconds: int | None = None


class DeviceCreate(BaseModel):
    location_id: int
    label: str
    ip_address: DeviceHost
    port: DevicePort = 4370
    serial_number: str | None = None
    device_type: DeviceType = "zkteco"
    auth_username: str | None = None
    auth_password: str | None = None
    is_active: bool = True


class DeviceUpdate(BaseModel):
    location_id: int | None = None
    label: str | None = None
    ip_address: DeviceHost | None = None
    port: DevicePort | None = None
    serial_number: str | None = None
    device_type: DeviceType | None = None
    auth_username: str | None = None
    auth_password: str | None = None
    is_active: bool | None = None


class DeviceTestConnectionResult(BaseModel):
    reachable: bool
    detail: str | None = None


class DeviceUserRow(BaseModel):
    device_user_id: str
    name: str
    linked_employee_id: int | None = None
    linked_employee_name: str | None = None


class DeviceUsersOut(BaseModel):
    location_id: int
    users: list[DeviceUserRow]


class InternalDeviceOut(BaseModel):
    """Worker-facing device shape (`/internal/devices`) — unlike DeviceOut,
    this includes auth_password, since worker genuinely needs it to
    authenticate to HTTP/ISAPI-style devices. Never exposed to the frontend
    (this endpoint is shared-secret protected, not cookie/CORS reachable —
    see routers/internal.py)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    location_name: str | None = None
    label: str
    ip_address: str
    port: int
    # Required by the hikvision_cloud adapter — the cloud API identifies a
    # device by serial, not by address.
    serial_number: str | None = None
    device_type: DeviceType
    auth_username: str | None = None
    auth_password: str | None = None


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------

EmploymentStatus = Literal["active", "inactive", "terminated"]


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int
    location_name: str | None = None
    employee_code: str
    first_name: str
    last_name: str
    national_id: str | None
    job_title: str | None
    hire_date: date
    base_salary_eur: float
    manager_user_id: int | None
    manager_name: str | None = None
    employment_status: EmploymentStatus


class EmployeeCreate(BaseModel):
    location_id: int
    employee_code: str
    first_name: str
    last_name: str
    national_id: str | None = None
    job_title: str | None = None
    hire_date: date
    base_salary_eur: float
    manager_user_id: int | None = None
    employment_status: EmploymentStatus = "active"


class EmployeeUpdate(BaseModel):
    location_id: int | None = None
    employee_code: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    national_id: str | None = None
    job_title: str | None = None
    hire_date: date | None = None
    base_salary_eur: float | None = None
    manager_user_id: int | None = None
    employment_status: EmploymentStatus | None = None


class EmployeeDeviceEnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    device_id: int
    device_label: str | None = None
    device_user_id: str
    enrolled_at: datetime | None


class EmployeeDeviceEnrollmentCreate(BaseModel):
    device_id: int
    device_user_id: str


class EmployeeShiftAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    shift_schedule_id: int
    shift_schedule_name: str | None = None
    effective_from: date
    effective_to: date | None


class EmployeeShiftAssignmentCreate(BaseModel):
    shift_schedule_id: int
    effective_from: date
    effective_to: date | None = None


class EmployeeShiftAssignmentUpdate(BaseModel):
    shift_schedule_id: int | None = None
    effective_from: date | None = None
    effective_to: date | None = None


# ---------------------------------------------------------------------------
# Shift schedules
# ---------------------------------------------------------------------------


class ShiftBreakWindowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int | None = None
    break_start_time: time
    break_end_time: time
    is_paid: bool


class ShiftBreakWindowIn(BaseModel):
    id: int | None = None
    break_start_time: time
    break_end_time: time
    is_paid: bool = False


class ShiftWorkWindowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int | None = None
    work_start_time: time
    work_end_time: time


class ShiftWorkWindowIn(BaseModel):
    work_start_time: time
    work_end_time: time


class ShiftScheduleDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int | None = None
    day_of_week: int
    is_working_day: bool
    # Derived outer bounds of the day (earliest window start, latest window
    # end). `work_windows` is the authoritative per-block list — a split shift
    # has more than one, and these two fields alone cannot express the gap.
    work_start_time: time | None
    work_end_time: time | None
    work_windows: list[ShiftWorkWindowOut] = []
    break_windows: list[ShiftBreakWindowOut] = []


class ShiftScheduleDayIn(BaseModel):
    id: int | None = None
    day_of_week: int
    is_working_day: bool
    # A client that knows about split shifts sends `work_windows`. One that
    # doesn't (or a single-block day) may still send just start/end, which is
    # treated as a one-window day.
    work_start_time: time | None = None
    work_end_time: time | None = None
    work_windows: list[ShiftWorkWindowIn] = []
    break_windows: list[ShiftBreakWindowIn] = []


class ShiftScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    location_name: str | None = None
    name: str
    grace_minutes_late: int
    is_active: bool
    days: list[ShiftScheduleDayOut] | None = None


class ShiftScheduleCreate(BaseModel):
    location_id: int | None = None
    name: str
    grace_minutes_late: int = 0
    is_active: bool = True


class ShiftScheduleUpdate(BaseModel):
    location_id: int | None = None
    name: str | None = None
    grace_minutes_late: int | None = None
    is_active: bool | None = None


class ShiftScheduleDaysReplace(BaseModel):
    days: list[ShiftScheduleDayIn]


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

PunchType = Literal[
    "check_in_work",
    "check_out_work",
    "check_in_break",
    "check_out_break",
    # Explicitly badged on the device ("start overtime" / "end overtime"),
    # as opposed to overtime inferred from the schedule — see migration 0014.
    "check_in_overtime",
    "check_out_overtime",
    "unclassified",
]


class AttendanceLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    device_id: int
    device_label: str | None = None
    device_user_id: str
    employee_id: int | None
    employee_name: str | None = None
    punch_timestamp: datetime
    raw_status_code: int
    punch_type: PunchType | None
    synced_at: datetime


class AttendanceLogResolve(BaseModel):
    employee_id: int


DailyStatusValue = Literal["present", "late", "absent", "on_leave", "holiday", "not_scheduled"]


class AttendanceDailyStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: str | None = None
    work_date: date
    shift_schedule_id: int | None
    scheduled_start: time | None
    scheduled_end: time | None
    actual_first_in: datetime | None
    actual_last_out: datetime | None
    late_minutes: int
    early_departure_minutes: int
    overtime_minutes: int
    break_minutes_taken: int
    status: DailyStatusValue
    is_absence_excused: bool | None
    # Overtime pre-approval. `overtime_requires_approval` reflects the
    # overtime_config effective for that employee/day, so the UI only shows a
    # pending state where approval actually gates payment.
    overtime_approved_at: datetime | None = None
    overtime_requires_approval: bool = False
    recompute_version: int
    computed_at: datetime


class AttendanceRecomputeRequest(BaseModel):
    date_from: date
    date_to: date
    employee_id: int | None = None


class SetExcusedRequest(BaseModel):
    is_absence_excused: bool


class SetOvertimeApprovalRequest(BaseModel):
    approved: bool


# ---------------------------------------------------------------------------
# Rota (shift templates + per-date roster)
# ---------------------------------------------------------------------------


class ShiftTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    location_name: str | None = None
    name: str
    work_start_time: time
    work_end_time: time
    break_start_time: time | None
    break_end_time: time | None
    break_is_paid: bool
    grace_minutes_late: int
    is_active: bool


class ShiftTemplateCreate(BaseModel):
    location_id: int | None = None
    name: str
    work_start_time: time
    work_end_time: time
    break_start_time: time | None = None
    break_end_time: time | None = None
    break_is_paid: bool = False
    grace_minutes_late: int = 0
    is_active: bool = True


class ShiftTemplateUpdate(BaseModel):
    location_id: int | None = None
    name: str | None = None
    work_start_time: time | None = None
    work_end_time: time | None = None
    break_start_time: time | None = None
    break_end_time: time | None = None
    break_is_paid: bool | None = None
    grace_minutes_late: int | None = None
    is_active: bool | None = None


class RosterEmployeeRow(BaseModel):
    employee_id: int
    employee_name: str
    # date (ISO) -> shift_template_id, or None for an explicit day off. A date
    # missing from the map has no rota entry (falls back to the weekly schedule).
    assignments: dict[str, int | None]


class RosterOut(BaseModel):
    location_id: int
    week_start: date
    dates: list[str]
    employees: list[RosterEmployeeRow]


class RosterEntryIn(BaseModel):
    employee_id: int
    work_date: date
    shift_template_id: int | None = None
    # True removes the entry entirely (falls back to the weekly schedule).
    clear: bool = False


class RosterReplace(BaseModel):
    entries: list[RosterEntryIn]


# ---------------------------------------------------------------------------
# Licence
# ---------------------------------------------------------------------------


class LicenseStatusOut(BaseModel):
    issued_to: str
    edition: str
    expires: date
    days_left: int
    expired: bool
    expiring_soon: bool


class LicenseInstall(BaseModel):
    key: str


# ---------------------------------------------------------------------------
# Holidays
# ---------------------------------------------------------------------------


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    location_name: str | None = None
    holiday_date: date
    name_en: str
    name_sq: str
    recurs_annually: bool


class HolidayCreate(BaseModel):
    # None = every location, same convention as the config tables.
    location_id: int | None = None
    holiday_date: date
    name_en: str
    name_sq: str
    # Fixed-date holidays (1 January) are entered once; moving ones (Eid,
    # Easter) are entered per year with this off.
    recurs_annually: bool = False


class HolidayUpdate(BaseModel):
    location_id: int | None = None
    holiday_date: date | None = None
    name_en: str | None = None
    name_sq: str | None = None
    recurs_annually: bool | None = None


# ---------------------------------------------------------------------------
# Leave
# ---------------------------------------------------------------------------


class LeaveTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name_en: str
    name_sq: str
    is_paid: bool
    annual_entitlement_days: float | None
    requires_approval: bool
    is_active: bool


class LeaveTypeCreate(BaseModel):
    name_en: str
    name_sq: str
    is_paid: bool
    annual_entitlement_days: float | None = None
    # Default false — client direction 2026-08-27: no approval workflow for
    # leave, a recorded leave request should immediately count the employee
    # as on_leave (see services/recompute.py's leave-precedence check and
    # reports.py's not_checked_in alert, which already skip anyone on
    # approved leave — this only affects how fast a request becomes
    # "approved" in the first place).
    requires_approval: bool = False
    is_active: bool = True


class LeaveTypeUpdate(BaseModel):
    name_en: str | None = None
    name_sq: str | None = None
    is_paid: bool | None = None
    annual_entitlement_days: float | None = None
    requires_approval: bool | None = None
    is_active: bool | None = None


LeaveStatus = Literal["pending", "approved", "rejected", "cancelled"]


class LeaveRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    employee_name: str | None = None
    leave_type_id: int
    leave_type_name_en: str | None = None
    leave_type_name_sq: str | None = None
    start_date: date
    end_date: date
    status: LeaveStatus
    requested_by_user_id: int
    requested_by_name: str | None = None
    approved_by_user_id: int | None
    approved_by_name: str | None = None
    approved_at: datetime | None
    notes: str | None


class LeaveRecordCreate(BaseModel):
    employee_id: int
    leave_type_id: int
    start_date: date
    end_date: date
    notes: str | None = None


class LeaveActionRequest(BaseModel):
    notes: str | None = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PenaltyRuleType = Literal["flat_per_minute", "threshold_allowance"]


class PenaltyConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    location_name: str | None = None
    rule_type: PenaltyRuleType
    rate_per_minute_eur: float | None
    allowance_minutes: int | None
    flat_amount_eur: float | None
    max_daily_penalty_eur: float | None
    early_departure_rate_per_minute_eur: float | None
    effective_from: date
    effective_to: date | None
    is_active: bool


class PenaltyConfigCreate(BaseModel):
    location_id: int | None = None
    rule_type: PenaltyRuleType
    rate_per_minute_eur: float | None = None
    allowance_minutes: int | None = None
    flat_amount_eur: float | None = None
    max_daily_penalty_eur: float | None = None
    early_departure_rate_per_minute_eur: float | None = 0
    effective_from: date
    effective_to: date | None = None
    is_active: bool = True


class PenaltyConfigUpdate(BaseModel):
    location_id: int | None = None
    rule_type: PenaltyRuleType | None = None
    rate_per_minute_eur: float | None = None
    allowance_minutes: int | None = None
    flat_amount_eur: float | None = None
    max_daily_penalty_eur: float | None = None
    early_departure_rate_per_minute_eur: float | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool | None = None


OvertimeThresholdBasis = Literal["daily", "weekly"]


class OvertimeConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    location_name: str | None = None
    threshold_basis: OvertimeThresholdBasis
    daily_threshold_minutes: int | None
    weekly_threshold_minutes: int | None
    rate_per_hour_eur: float
    weekend_rate_per_hour_eur: float | None
    holiday_rate_per_hour_eur: float | None
    requires_preapproval: bool
    monthly_cap_minutes: int | None
    effective_from: date
    effective_to: date | None
    is_active: bool


class OvertimeConfigCreate(BaseModel):
    location_id: int | None = None
    threshold_basis: OvertimeThresholdBasis
    daily_threshold_minutes: int | None = None
    weekly_threshold_minutes: int | None = None
    rate_per_hour_eur: float
    weekend_rate_per_hour_eur: float | None = None
    holiday_rate_per_hour_eur: float | None = None
    requires_preapproval: bool = False
    monthly_cap_minutes: int | None = None
    effective_from: date
    effective_to: date | None = None
    is_active: bool = True


class OvertimeConfigUpdate(BaseModel):
    location_id: int | None = None
    threshold_basis: OvertimeThresholdBasis | None = None
    daily_threshold_minutes: int | None = None
    weekly_threshold_minutes: int | None = None
    rate_per_hour_eur: float | None = None
    weekend_rate_per_hour_eur: float | None = None
    holiday_rate_per_hour_eur: float | None = None
    requires_preapproval: bool | None = None
    monthly_cap_minutes: int | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool | None = None


AbsenceDeductionBasis = Literal["flat_amount", "full_day_salary_fraction"]


class AbsenceRuleConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    location_name: str | None = None
    rule_type: str
    deduction_basis: AbsenceDeductionBasis
    deduction_value: float
    effective_from: date
    effective_to: date | None
    is_active: bool


class AbsenceRuleConfigCreate(BaseModel):
    location_id: int | None = None
    rule_type: str = "no_punch_no_leave"
    deduction_basis: AbsenceDeductionBasis
    deduction_value: float
    effective_from: date
    effective_to: date | None = None
    is_active: bool = True


class AbsenceRuleConfigUpdate(BaseModel):
    location_id: int | None = None
    rule_type: str | None = None
    deduction_basis: AbsenceDeductionBasis | None = None
    deduction_value: float | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class AppUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: Role
    employee_id: int | None
    employee_name: str | None = None
    location_id: int | None = None
    location_name: str | None = None
    is_active: bool
    last_login_at: datetime | None
    must_change_password: bool


class AppUserCreate(BaseModel):
    username: str
    # SECURITY: minimum length floor — see SECURITY_REPORT.md "no password
    # strength/length validation".
    password: str = Field(min_length=8)
    role: Role
    employee_id: int | None = None
    # Added 2026-08-22, client-directed access-control change (BLUEPRINT.md
    # Section 3.14/6.4) — a manager's assigned location, drives location-based
    # visibility scoping. Not applicable to admin.
    location_id: int | None = None
    is_active: bool = True


class AppUserUpdate(BaseModel):
    role: Role | None = None
    employee_id: int | None = None
    location_id: int | None = None
    is_active: bool | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


# ---------------------------------------------------------------------------
# Payroll
# ---------------------------------------------------------------------------

PayrollRunStatus = Literal["draft", "finalized"]


class PayrollRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    location_id: int | None
    location_name: str | None = None
    period_year: int
    period_month: int
    status: PayrollRunStatus
    generated_by_user_id: int
    generated_by_name: str | None = None
    finalized_at: datetime | None
    line_count: int | None = None
    total_net_pay_eur: float | None = None


class PayrollRunCreate(BaseModel):
    period_year: int
    period_month: int
    location_id: int


class PayrollRunLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    payroll_run_id: int
    employee_id: int
    employee_name: str | None = None
    base_salary_eur: float
    total_late_minutes: int
    total_lateness_penalty_eur: float
    total_overtime_minutes: int
    total_overtime_bonus_eur: float
    total_absence_days: float
    total_absence_deduction_eur: float
    paid_leave_days: float
    unpaid_leave_days: float
    net_pay_eur: float


AdjustmentType = Literal["bonus", "deduction"]


class PayrollAdjustmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    payroll_run_line_id: int
    type: AdjustmentType
    amount_eur: float
    reason: str
    created_by_user_id: int
    created_by_name: str | None = None


class PayrollAdjustmentCreate(BaseModel):
    type: AdjustmentType
    amount_eur: float
    reason: str


class PayrollRunLineDetailOut(PayrollRunLineOut):
    adjustments: list[PayrollAdjustmentOut] = []


# ---------------------------------------------------------------------------
# Internal (worker -> api)
# ---------------------------------------------------------------------------


class InternalEnrollmentOut(BaseModel):
    employee_id: int
    employee_name: str
    device_user_id: str


PunchType = Literal[
    "check_in_work",
    "check_out_work",
    "check_in_break",
    "check_out_break",
    "check_in_overtime",
    "check_out_overtime",
]


class IngestPunch(BaseModel):
    device_id: int
    device_user_id: str
    punch_timestamp: datetime
    raw_status_code: int
    # Set by vendors whose protocol already classifies the punch (e.g.
    # Hikvision ISAPI's attendanceStatus) — see services/classify.py.
    punch_type_hint: PunchType | None = None


class IngestPunchesRequest(BaseModel):
    punches: list[IngestPunch]


class IngestPunchesResult(BaseModel):
    inserted: int
    duplicates: int
    unresolved: int


class ProcessDailyStatusRequest(BaseModel):
    work_date: date


class ProcessDailyStatusResult(BaseModel):
    processed_employees: int


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


class DashboardSummaryOut(BaseModel):
    present_today: int
    on_site_now: int
    late_today: int
    absent_today: int
    on_leave_today: int
    on_leave_employees: list[OnLeaveEmployee]
    on_break_now: int
    on_break_employees: list[OnBreakEmployee]
    pending_leave_count: int
    pending_leave: list[LeaveRecordOut]
    pending_leave_total: int


class AttendanceTrendDay(BaseModel):
    work_date: date
    present: int
    late: int
    absent: int
    on_leave: int


class TopLateEmployee(BaseModel):
    employee_id: int
    employee_name: str
    total_late_minutes: int
    late_days: int


class TopOvertimeEmployee(BaseModel):
    employee_id: int
    employee_name: str
    total_overtime_minutes: int
    overtime_days: int


class OnBreakEmployee(BaseModel):
    employee_id: int
    employee_name: str
    break_started_at: datetime


class OnLeaveEmployee(BaseModel):
    employee_id: int
    employee_name: str
    leave_type_name_en: str
    leave_type_name_sq: str
    start_date: date
    end_date: date


class AlertItem(BaseModel):
    type: str
    severity: Literal["warning", "danger"]
    message: str
    employee_id: int | None = None
    employee_name: str | None = None
    work_date: date | None = None
    # The specific time the underlying event happened (a punch, a device's
    # last sync, ...) — not every alert type has one (e.g. manager_no_location
    # is a standing state, not a moment in time), so this stays optional.
    # work_date remains the field used for links/sorting.
    occurred_at: datetime | None = None
    link: str | None = None
    # Structured data for the frontend to build a translated message from
    # `type` (the `message` field above is English-only, used as a fallback
    # for any consumer that doesn't know how to render a given `type`).
    count: int | None = None
    device_label: str | None = None
    username: str | None = None


class AlertsOut(BaseModel):
    alerts: list[AlertItem]
    count: int


class AnalyticsOut(BaseModel):
    attendance_trend: list[AttendanceTrendDay]
    avg_late_minutes: float
    total_overtime_minutes: int
    top_late_employees: list[TopLateEmployee]
    top_overtime_employees: list[TopOvertimeEmployee]
