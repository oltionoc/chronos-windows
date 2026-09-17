"""SQLAlchemy models — mirrors BLUEPRINT.md Section 3 exactly.

Enums are stored as plain VARCHAR + CHECK constraint (native_enum=False)
rather than native Postgres ENUM types, to keep Alembic migrations simple
(no ALTER TYPE dance when a value set changes) — a deliberate simplification,
not specified either way by BLUEPRINT.md.
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _enum(*values: str):
    return String()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Location(TimestampMixin, Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, server_default="Europe/Tirane")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Device(TimestampMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint(
            "device_type in ('zkteco','hikvision','hikvision_cloud')", name="ck_device_type"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # Was Postgres INET — widened to plain text 2026-09-16 so this can hold a
    # DDNS hostname (e.g. a Hikvision device reachable via the vendor's
    # cloud/DDNS relay, no static LAN IP) as well as a literal IP. Validated
    # loosely at the app layer, not by the DB.
    ip_address: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, server_default="4370")
    serial_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 2026-09-16: multi-vendor support. 'zkteco' (pyzk/TCP 4370, the original
    # K40 integration), 'hikvision' (ISAPI over HTTP, digest auth, device
    # reached directly) or 'hikvision_cloud' (Hik-Connect Open Platform, the
    # device reached through Hikvision's cloud instead of directly) — worker
    # dispatches to the matching adapter per device (worker/worker/sync.py).
    # For 'hikvision_cloud', ip_address/port hold the *cloud API* host/port
    # rather than the device's own address, auth_username/auth_password hold
    # the Open Platform appKey/appSecret, and serial_number identifies which
    # device to pull events for — see worker/worker/adapters/hikvision_cloud.py.
    device_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="zkteco")
    # Only used by HTTP-style vendors (Hikvision direct + cloud).
    # SECURITY: stored in plaintext, same posture as this app's other
    # shared-secret env vars — acceptable for the Phase 1 LAN-only/internal
    # threat model, but flagged here since it's now DB-resident rather than
    # env-resident. Revisit before any internet-facing deployment.
    auth_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    auth_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Seconds the device's own clock is AHEAD of the server's (negative =
    # behind), measured by the worker on each sync (migration 0012). NULL is
    # "not measured" — the vendor exposes no clock endpoint, or the read
    # failed — which is deliberately different from a measured 0.
    clock_skew_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clock_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    location: Mapped["Location"] = relationship()


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role in ('admin','manager')", name="ck_users_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", use_alter=True, name="fk_users_employee_id"), nullable=True
    )
    # Added 2026-08-22, client-directed access-control change (BLUEPRINT.md
    # Section 3.14 / 6.2): a Manager's assigned location — drives
    # location-based visibility scoping. Nullable: admin never needs it;
    # a manager row may also be temporarily null.
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SECURITY (SECURITY_REPORT.md — "bootstrap admin credential"): forces a
    # password change before the account can use any endpoint other than
    # /auth/*. Set True whenever HR/Admin sets a user's password on their
    # behalf (initial creation, reset-password); cleared when the user
    # successfully changes their own password via PATCH /auth/me/password.
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    employee: Mapped["Employee | None"] = relationship(foreign_keys=[employee_id])
    location: Mapped["Location | None"] = relationship()


class Employee(TimestampMixin, Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint(
            "employment_status in ('active','inactive','terminated')", name="ck_employees_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)
    employee_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    national_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    hire_date: Mapped[str] = mapped_column(Date, nullable=False)
    base_salary_eur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    employment_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")

    location: Mapped["Location"] = relationship()
    manager: Mapped["User | None"] = relationship(foreign_keys=[manager_user_id])


class EmployeeDeviceEnrollment(TimestampMixin, Base):
    __tablename__ = "employee_device_enrollments"
    __table_args__ = (UniqueConstraint("device_id", "device_user_id", name="uq_device_enrollment"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    device_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    employee: Mapped["Employee"] = relationship()
    device: Mapped["Device"] = relationship()


class ShiftSchedule(TimestampMixin, Base):
    __tablename__ = "shift_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    grace_minutes_late: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    location: Mapped["Location | None"] = relationship()
    days: Mapped[list["ShiftScheduleDay"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan", order_by="ShiftScheduleDay.day_of_week"
    )


class ShiftScheduleDay(TimestampMixin, Base):
    __tablename__ = "shift_schedule_days"
    __table_args__ = (
        UniqueConstraint("shift_schedule_id", "day_of_week", name="uq_shift_schedule_day"),
        CheckConstraint("day_of_week >= 0 and day_of_week <= 6", name="ck_day_of_week_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shift_schedule_id: Mapped[int] = mapped_column(ForeignKey("shift_schedules.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    is_working_day: Mapped[bool] = mapped_column(Boolean, nullable=False)
    work_start_time: Mapped[str | None] = mapped_column(Time, nullable=True)
    work_end_time: Mapped[str | None] = mapped_column(Time, nullable=True)

    schedule: Mapped["ShiftSchedule"] = relationship(back_populates="days")
    break_windows: Mapped[list["ShiftBreakWindow"]] = relationship(
        back_populates="day", cascade="all, delete-orphan"
    )
    work_windows: Mapped[list["ShiftWorkWindow"]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="ShiftWorkWindow.sort_order"
    )


class ShiftWorkWindow(TimestampMixin, Base):
    """One work block within a weekday. A normal day has exactly one; a split
    shift (common in hospitality: 08:00-12:00, back at 17:00-21:00) has
    several. `shift_schedule_days.work_start_time/work_end_time` remain as the
    day's derived outer bounds — see migration 0011 — so this is the only
    place per-block times live."""

    __tablename__ = "shift_work_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shift_schedule_day_id: Mapped[int] = mapped_column(
        ForeignKey("shift_schedule_days.id", ondelete="CASCADE"), nullable=False
    )
    work_start_time: Mapped[str] = mapped_column(Time, nullable=False)
    work_end_time: Mapped[str] = mapped_column(Time, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    day: Mapped["ShiftScheduleDay"] = relationship(back_populates="work_windows")


class ShiftBreakWindow(TimestampMixin, Base):
    __tablename__ = "shift_break_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    shift_schedule_day_id: Mapped[int] = mapped_column(ForeignKey("shift_schedule_days.id"), nullable=False)
    break_start_time: Mapped[str] = mapped_column(Time, nullable=False)
    break_end_time: Mapped[str] = mapped_column(Time, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    day: Mapped["ShiftScheduleDay"] = relationship(back_populates="break_windows")


class EmployeeShiftAssignment(TimestampMixin, Base):
    __tablename__ = "employee_shift_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    shift_schedule_id: Mapped[int] = mapped_column(ForeignKey("shift_schedules.id"), nullable=False)
    effective_from: Mapped[str] = mapped_column(Date, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(Date, nullable=True)

    employee: Mapped["Employee"] = relationship()
    shift_schedule: Mapped["ShiftSchedule"] = relationship()


class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    __table_args__ = (
        UniqueConstraint(
            "device_id", "device_user_id", "punch_timestamp", "raw_status_code", name="uq_attendance_log_dedup"
        ),
        CheckConstraint(
            "punch_type in ('check_in_work','check_out_work','check_in_break','check_out_break',"
            "'check_in_overtime','check_out_overtime','unclassified') "
            "or punch_type is null",
            name="ck_punch_type",
        ),
        CheckConstraint(
            "punch_type_hint in ('check_in_work','check_out_work','check_in_break','check_out_break',"
            "'check_in_overtime','check_out_overtime') "
            "or punch_type_hint is null",
            name="ck_punch_type_hint",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), nullable=False)
    device_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    punch_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    punch_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Some device vendors (e.g. Hikvision ISAPI's `attendanceStatus`) already
    # tell us exactly what kind of punch this is, instead of a bare numeric
    # status code we have to infer from (ZKTeco's approach — see
    # services/classify.py). When set, classify_employee_date trusts this
    # directly instead of running the alternating-parity/break-window
    # heuristic. Null for ZKTeco and any vendor that doesn't self-classify.
    punch_type_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    device: Mapped["Device"] = relationship()
    employee: Mapped["Employee | None"] = relationship()


class AttendanceDailyStatus(TimestampMixin, Base):
    __tablename__ = "attendance_daily_status"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_daily_status_employee_date"),
        CheckConstraint(
            "status in ('present','late','absent','on_leave','holiday','not_scheduled')",
            name="ck_daily_status_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    work_date: Mapped[str] = mapped_column(Date, nullable=False)
    shift_schedule_id: Mapped[int | None] = mapped_column(ForeignKey("shift_schedules.id"), nullable=True)
    scheduled_start: Mapped[str | None] = mapped_column(Time, nullable=True)
    scheduled_end: Mapped[str | None] = mapped_column(Time, nullable=True)
    actual_first_in: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_last_out: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    early_departure_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    break_minutes_taken: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    is_absence_excused: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Overtime pre-approval (migration 0011). Only consulted when the
    # effective overtime_config has requires_preapproval = true; otherwise
    # overtime pays regardless. Cleared automatically whenever a recompute
    # changes overtime_minutes, so nobody's approval silently carries over to
    # a different number than the one they saw.
    overtime_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    overtime_approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    recompute_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    employee: Mapped["Employee"] = relationship()
    shift_schedule: Mapped["ShiftSchedule | None"] = relationship()


class Holiday(TimestampMixin, Base):
    """A public holiday. `location_id` NULL means every location, the same
    convention penalty/overtime/absence config already use.

    `recurs_annually` covers fixed-date holidays (1 January) so they are
    entered once; moving ones (Eid, Easter) are entered per year with it off.
    See services/holiday_lookup.py for the matching rule and migration 0013
    for why this table did not exist until now."""

    __tablename__ = "holidays"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    holiday_date: Mapped[date] = mapped_column(Date, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_sq: Mapped[str] = mapped_column(Text, nullable=False)
    recurs_annually: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    location: Mapped["Location | None"] = relationship()


class LeaveType(TimestampMixin, Base):
    __tablename__ = "leave_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Bilingual name — this app has no server-side locale (i18n is
    # frontend-only), so both are always returned and the frontend picks
    # which one to display based on the active UI language.
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    name_sq: Mapped[str] = mapped_column(Text, nullable=False)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    annual_entitlement_days: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class LeaveRecord(TimestampMixin, Base):
    __tablename__ = "leave_records"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending','approved','rejected','cancelled')", name="ck_leave_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    leave_type_id: Mapped[int] = mapped_column(ForeignKey("leave_types.id"), nullable=False)
    start_date: Mapped[str] = mapped_column(Date, nullable=False)
    end_date: Mapped[str] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    requested_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    employee: Mapped["Employee"] = relationship()
    leave_type: Mapped["LeaveType"] = relationship()
    requested_by: Mapped["User"] = relationship(foreign_keys=[requested_by_user_id])
    approved_by: Mapped["User | None"] = relationship(foreign_keys=[approved_by_user_id])


class PenaltyConfig(TimestampMixin, Base):
    __tablename__ = "penalty_config"
    __table_args__ = (
        CheckConstraint("rule_type in ('flat_per_minute','threshold_allowance')", name="ck_penalty_rule_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    rate_per_minute_eur: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    allowance_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flat_amount_eur: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    max_daily_penalty_eur: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    early_departure_rate_per_minute_eur: Mapped[float | None] = mapped_column(
        Numeric(8, 2), nullable=True, server_default="0"
    )
    effective_from: Mapped[str] = mapped_column(Date, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    location: Mapped["Location | None"] = relationship()


class OvertimeConfig(TimestampMixin, Base):
    __tablename__ = "overtime_config"
    __table_args__ = (
        CheckConstraint("threshold_basis in ('daily','weekly')", name="ck_overtime_threshold_basis"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    threshold_basis: Mapped[str] = mapped_column(Text, nullable=False)
    daily_threshold_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekly_threshold_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_per_hour_eur: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    weekend_rate_per_hour_eur: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    holiday_rate_per_hour_eur: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    requires_preapproval: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    monthly_cap_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    effective_from: Mapped[str] = mapped_column(Date, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    location: Mapped["Location | None"] = relationship()


class AbsenceRuleConfig(TimestampMixin, Base):
    __tablename__ = "absence_rule_config"
    __table_args__ = (
        CheckConstraint(
            "deduction_basis in ('flat_amount','full_day_salary_fraction')", name="ck_absence_deduction_basis"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="no_punch_no_leave")
    deduction_basis: Mapped[str] = mapped_column(Text, nullable=False)
    deduction_value: Mapped[float] = mapped_column(Numeric(8, 2), nullable=False)
    effective_from: Mapped[str] = mapped_column(Date, nullable=False)
    effective_to: Mapped[str | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    location: Mapped["Location | None"] = relationship()


class PayrollRun(TimestampMixin, Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("location_id", "period_year", "period_month", name="uq_payroll_run_period"),
        CheckConstraint("status in ('draft','finalized')", name="ck_payroll_run_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="draft")
    generated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    location: Mapped["Location | None"] = relationship()
    generated_by: Mapped["User"] = relationship()
    lines: Mapped[list["PayrollRunLine"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class PayrollRunLine(Base):
    __tablename__ = "payroll_run_lines"
    __table_args__ = (UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_run_line"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_run_id: Mapped[int] = mapped_column(ForeignKey("payroll_runs.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), nullable=False)
    base_salary_eur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    total_late_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_lateness_penalty_eur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    total_overtime_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    total_overtime_bonus_eur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    total_absence_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, server_default="0")
    total_absence_deduction_eur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    paid_leave_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, server_default="0")
    unpaid_leave_days: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, server_default="0")
    net_pay_eur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    run: Mapped["PayrollRun"] = relationship(back_populates="lines")
    employee: Mapped["Employee"] = relationship()
    adjustments: Mapped[list["PayrollAdjustment"]] = relationship(
        back_populates="line", cascade="all, delete-orphan"
    )


class PayrollAdjustment(Base):
    __tablename__ = "payroll_adjustments"
    __table_args__ = (CheckConstraint("type in ('bonus','deduction')", name="ck_adjustment_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payroll_run_line_id: Mapped[int] = mapped_column(ForeignKey("payroll_run_lines.id"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    amount_eur: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    line: Mapped["PayrollRunLine"] = relationship(back_populates="adjustments")
    created_by: Mapped["User"] = relationship()
