"""initial schema — BLUEPRINT.md Section 3 (all 19 tables) + Phase 1 seed data

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-22

"""
from datetime import date, datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET

# revision identifiers, used by Alembic.
revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _ts_cols():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def upgrade() -> None:
    # ---- locations ----
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("timezone", sa.Text, nullable=False, server_default="Europe/Tirane"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        *_ts_cols(),
    )

    # ---- devices ----
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("ip_address", INET, nullable=False),
        sa.Column("port", sa.Integer, nullable=False, server_default="4370"),
        sa.Column("serial_number", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        *_ts_cols(),
    )

    # ---- users (employee_id FK added after employees exists) ----
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("employee_id", sa.Integer, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        # SECURITY: forces a password change before the account can use
        # anything other than /auth/* — see SECURITY_REPORT.md "bootstrap
        # admin credential".
        sa.Column("must_change_password", sa.Boolean, nullable=False, server_default="false"),
        sa.CheckConstraint("role in ('admin','manager')", name="ck_users_role"),
        *_ts_cols(),
    )

    # ---- employees ----
    op.create_table(
        "employees",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("employee_code", sa.Text, nullable=False, unique=True),
        sa.Column("first_name", sa.Text, nullable=False),
        sa.Column("last_name", sa.Text, nullable=False),
        sa.Column("national_id", sa.Text, nullable=True),
        sa.Column("hire_date", sa.Date, nullable=False),
        sa.Column("base_salary_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("manager_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("employment_status", sa.Text, nullable=False, server_default="active"),
        sa.CheckConstraint(
            "employment_status in ('active','inactive','terminated')", name="ck_employees_status"
        ),
        *_ts_cols(),
    )

    op.create_foreign_key(
        "fk_users_employee_id", "users", "employees", ["employee_id"], ["id"]
    )

    # ---- employee_device_enrollments ----
    op.create_table(
        "employee_device_enrollments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("device_id", sa.Integer, sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("device_user_id", sa.Text, nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("device_id", "device_user_id", name="uq_device_enrollment"),
        *_ts_cols(),
    )

    # ---- shift_schedules ----
    op.create_table(
        "shift_schedules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("grace_minutes_late", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        *_ts_cols(),
    )

    # ---- shift_schedule_days ----
    op.create_table(
        "shift_schedule_days",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shift_schedule_id", sa.Integer, sa.ForeignKey("shift_schedules.id"), nullable=False),
        sa.Column("day_of_week", sa.Integer, nullable=False),
        sa.Column("is_working_day", sa.Boolean, nullable=False),
        sa.Column("work_start_time", sa.Time, nullable=True),
        sa.Column("work_end_time", sa.Time, nullable=True),
        sa.UniqueConstraint("shift_schedule_id", "day_of_week", name="uq_shift_schedule_day"),
        sa.CheckConstraint("day_of_week >= 0 and day_of_week <= 6", name="ck_day_of_week_range"),
        *_ts_cols(),
    )

    # ---- shift_break_windows ----
    op.create_table(
        "shift_break_windows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("shift_schedule_day_id", sa.Integer, sa.ForeignKey("shift_schedule_days.id"), nullable=False),
        sa.Column("break_start_time", sa.Time, nullable=False),
        sa.Column("break_end_time", sa.Time, nullable=False),
        sa.Column("is_paid", sa.Boolean, nullable=False, server_default="false"),
        *_ts_cols(),
    )

    # ---- employee_shift_assignments ----
    op.create_table(
        "employee_shift_assignments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("shift_schedule_id", sa.Integer, sa.ForeignKey("shift_schedules.id"), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        *_ts_cols(),
    )

    # ---- attendance_logs ----
    op.create_table(
        "attendance_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_id", sa.Integer, sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("device_user_id", sa.Text, nullable=False),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id"), nullable=True),
        sa.Column("punch_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_status_code", sa.Integer, nullable=False),
        sa.Column("punch_type", sa.Text, nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "device_id", "device_user_id", "punch_timestamp", "raw_status_code", name="uq_attendance_log_dedup"
        ),
        sa.CheckConstraint(
            "punch_type in ('check_in_work','check_out_work','check_in_break','check_out_break','unclassified') "
            "or punch_type is null",
            name="ck_punch_type",
        ),
    )
    op.create_index("ix_attendance_logs_employee_punch", "attendance_logs", ["employee_id", "punch_timestamp"])

    # ---- attendance_daily_status ----
    op.create_table(
        "attendance_daily_status",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("work_date", sa.Date, nullable=False),
        sa.Column("shift_schedule_id", sa.Integer, sa.ForeignKey("shift_schedules.id"), nullable=True),
        sa.Column("scheduled_start", sa.Time, nullable=True),
        sa.Column("scheduled_end", sa.Time, nullable=True),
        sa.Column("actual_first_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_last_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("late_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("early_departure_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("overtime_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("break_minutes_taken", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("is_absence_excused", sa.Boolean, nullable=True),
        sa.Column("recompute_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("employee_id", "work_date", name="uq_daily_status_employee_date"),
        sa.CheckConstraint(
            "status in ('present','late','absent','on_leave','holiday','not_scheduled')",
            name="ck_daily_status_status",
        ),
        *_ts_cols(),
    )

    # ---- leave_types ----
    op.create_table(
        "leave_types",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("is_paid", sa.Boolean, nullable=False),
        sa.Column("annual_entitlement_days", sa.Numeric(5, 1), nullable=True),
        sa.Column("requires_approval", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        *_ts_cols(),
    )

    # ---- leave_records ----
    op.create_table(
        "leave_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("leave_type_id", sa.Integer, sa.ForeignKey("leave_types.id"), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="pending"),
        sa.Column("requested_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.CheckConstraint("status in ('pending','approved','rejected','cancelled')", name="ck_leave_status"),
        *_ts_cols(),
    )

    # ---- penalty_config ----
    op.create_table(
        "penalty_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("rule_type", sa.Text, nullable=False),
        sa.Column("rate_per_minute_eur", sa.Numeric(8, 2), nullable=True),
        sa.Column("allowance_minutes", sa.Integer, nullable=True),
        sa.Column("flat_amount_eur", sa.Numeric(8, 2), nullable=True),
        sa.Column("max_daily_penalty_eur", sa.Numeric(8, 2), nullable=True),
        sa.Column("early_departure_rate_per_minute_eur", sa.Numeric(8, 2), nullable=True, server_default="0"),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.CheckConstraint("rule_type in ('flat_per_minute','threshold_allowance')", name="ck_penalty_rule_type"),
        *_ts_cols(),
    )

    # ---- overtime_config ----
    op.create_table(
        "overtime_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("threshold_basis", sa.Text, nullable=False),
        sa.Column("daily_threshold_minutes", sa.Integer, nullable=True),
        sa.Column("weekly_threshold_minutes", sa.Integer, nullable=True),
        sa.Column("rate_per_hour_eur", sa.Numeric(8, 2), nullable=False),
        sa.Column("weekend_rate_per_hour_eur", sa.Numeric(8, 2), nullable=True),
        sa.Column("holiday_rate_per_hour_eur", sa.Numeric(8, 2), nullable=True),
        sa.Column("requires_preapproval", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("monthly_cap_minutes", sa.Integer, nullable=True),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.CheckConstraint("threshold_basis in ('daily','weekly')", name="ck_overtime_threshold_basis"),
        *_ts_cols(),
    )

    # ---- absence_rule_config ----
    op.create_table(
        "absence_rule_config",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("rule_type", sa.Text, nullable=False, server_default="no_punch_no_leave"),
        sa.Column("deduction_basis", sa.Text, nullable=False),
        sa.Column("deduction_value", sa.Numeric(8, 2), nullable=False),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.CheckConstraint(
            "deduction_basis in ('flat_amount','full_day_salary_fraction')", name="ck_absence_deduction_basis"
        ),
        *_ts_cols(),
    )

    # ---- payroll_runs ----
    op.create_table(
        "payroll_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("period_year", sa.Integer, nullable=False),
        sa.Column("period_month", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("generated_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("location_id", "period_year", "period_month", name="uq_payroll_run_period"),
        sa.CheckConstraint("status in ('draft','finalized')", name="ck_payroll_run_status"),
        *_ts_cols(),
    )

    # ---- payroll_run_lines ----
    op.create_table(
        "payroll_run_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payroll_run_id", sa.Integer, sa.ForeignKey("payroll_runs.id"), nullable=False),
        sa.Column("employee_id", sa.Integer, sa.ForeignKey("employees.id"), nullable=False),
        sa.Column("base_salary_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_late_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_lateness_penalty_eur", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("total_overtime_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_overtime_bonus_eur", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("total_absence_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("total_absence_deduction_eur", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("paid_leave_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("unpaid_leave_days", sa.Numeric(5, 1), nullable=False, server_default="0"),
        sa.Column("net_pay_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("payslip_pdf_path", sa.Text, nullable=True),
        sa.UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_run_line"),
    )

    # ---- payroll_adjustments ----
    op.create_table(
        "payroll_adjustments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("payroll_run_line_id", sa.Integer, sa.ForeignKey("payroll_run_lines.id"), nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("amount_eur", sa.Numeric(10, 2), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("created_by_user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("type in ('bonus','deduction')", name="ck_adjustment_type"),
    )

    _seed_data()


def _seed_data() -> None:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    locations = sa.table(
        "locations",
        sa.column("id", sa.Integer),
        sa.column("name", sa.Text),
        sa.column("address", sa.Text),
        sa.column("timezone", sa.Text),
        sa.column("is_active", sa.Boolean),
    )
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("username", sa.Text),
        sa.column("password_hash", sa.Text),
        sa.column("role", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("must_change_password", sa.Boolean),
    )
    absence_rule_config = sa.table(
        "absence_rule_config",
        sa.column("location_id", sa.Integer),
        sa.column("rule_type", sa.Text),
        sa.column("deduction_basis", sa.Text),
        sa.column("deduction_value", sa.Numeric),
        sa.column("effective_from", sa.Date),
        sa.column("is_active", sa.Boolean),
    )

    # BLUEPRINT.md Section 8/9: the client's on-site PC has no pre-existing
    # login accounts, so a single bootstrap location + admin account is
    # seeded here purely to make the freshly-migrated system reachable via
    # the login screen. This is an operational bootstrap step, not a
    # business-rule default. SECURITY: the seeded password is a well-known
    # default, so `must_change_password=True` forces it to be changed before
    # the account can do anything else — see SECURITY_REPORT.md "bootstrap
    # admin credential". This is enforced server-side, not just documented.
    op.bulk_insert(
        locations,
        [
            {
                "id": 1,
                "name": "Main Location",
                "address": None,
                "timezone": "Europe/Tirane",
                "is_active": True,
            }
        ],
    )
    op.execute(sa.text("SELECT setval('locations_id_seq', 1)"))

    op.bulk_insert(
        users,
        [
            {
                "id": 1,
                "username": "admin",
                "password_hash": pwd_context.hash("ChangeMe123!"),
                "role": "admin",
                "is_active": True,
                "must_change_password": True,
            }
        ],
    )
    op.execute(sa.text("SELECT setval('users_id_seq', 1)"))

    # Phase 1 seed value per BLUEPRINT.md Section 3.13 / 10 — a *default*,
    # not a client-confirmed policy. Remains editable via /config/absence-rule.
    op.bulk_insert(
        absence_rule_config,
        [
            {
                "location_id": None,
                "rule_type": "no_punch_no_leave",
                "deduction_basis": "full_day_salary_fraction",
                "deduction_value": 1.0,
                "effective_from": date(2020, 1, 1),
                "is_active": True,
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("payroll_adjustments")
    op.drop_table("payroll_run_lines")
    op.drop_table("payroll_runs")
    op.drop_table("absence_rule_config")
    op.drop_table("overtime_config")
    op.drop_table("penalty_config")
    op.drop_table("leave_records")
    op.drop_table("leave_types")
    op.drop_table("attendance_daily_status")
    op.drop_index("ix_attendance_logs_employee_punch", table_name="attendance_logs")
    op.drop_table("attendance_logs")
    op.drop_table("employee_shift_assignments")
    op.drop_table("shift_break_windows")
    op.drop_table("shift_schedule_days")
    op.drop_table("shift_schedules")
    op.drop_table("employee_device_enrollments")
    op.drop_constraint("fk_users_employee_id", "users", type_="foreignkey")
    op.drop_table("employees")
    op.drop_table("users")
    op.drop_table("devices")
    op.drop_table("locations")
