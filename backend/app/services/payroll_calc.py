"""Monthly payroll computation — BLUEPRINT.md Section 5.5.

ASSUMPTIONS made where BLUEPRINT.md left the exact formula unspecified
(business-rule values themselves stay DB-configurable per Discovery.md
Section 10 — only the *aggregation algorithm* below is a backend judgment
call, documented here and in BACKEND_NOTES.md):

- Lateness penalty: computed per day from the `penalty_config` row effective
  on that specific day (per BLUEPRINT 5.5's "active... whose window covers
  each individual day"). `flat_per_minute` = late_minutes * rate. threshold_
  allowance = flat_amount_eur once late_minutes exceeds allowance_minutes,
  else 0. `max_daily_penalty_eur` caps the *lateness* component only (not
  early-departure, which has its own independent rate). Early-departure
  penalty = early_departure_minutes * early_departure_rate_per_minute_eur
  (defaults to 0 per BLUEPRINT 3.11), added to the lateness component to
  form `total_lateness_penalty_eur` (BLUEPRINT's schema has no separate
  early-departure column, so it is folded into the same total).
- Overtime: when `overtime_config.requires_preapproval` is set, only days
  carrying an `overtime_approved_at` contribute to pay; the rest stay
  recorded but unpaid until approved (added 2026-09-17 — the flag existed in
  the schema from Phase 1 but nothing consulted it).
  `attendance_daily_status.overtime_minutes` is already threshold-
  adjusted at the day level when `overtime_config.threshold_basis = 'daily'`
  (see services/recompute.py). When `threshold_basis = 'weekly'`, raw daily
  minutes are summed per ISO week and `weekly_threshold_minutes` is
  subtracted once per week; the weekday/weekend split of the resulting
  (possibly reduced) total is apportioned using each week's weekday/weekend
  minute ratio. `monthly_cap_minutes`, if set, scales the whole-month total
  (and its weekday/weekend/holiday split) down proportionally.
  `holiday_rate_per_hour_eur` IS applied as of 2026-09-17: migration 0013
  added the `holidays` table that was the missing data source, so work on a
  public holiday forms its own bucket paid at that rate, falling back to the
  ordinary rate when it is unset (never to the weekend rate — an unset
  holiday rate means "not configured", and quietly applying the weekend
  premium would be inventing a policy nobody chose).
- Absence deduction: one deduction per `attendance_daily_status` row with
  `status = 'absent'` and `is_absence_excused` not True, using the
  `absence_rule_config` row effective on that day. `full_day_salary_fraction`
  converts to euros via `base_salary_eur / days_in_month * deduction_value`.
- Leave days: counted from `attendance_daily_status` rows with
  `status = 'on_leave'` in the period (this status is only ever set by
  `recompute.py` for scheduled working days covered by an approved leave
  record), split into paid/unpaid via the covering leave record's
  `leave_types.is_paid`.
"""
import calendar
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AbsenceRuleConfig,
    AttendanceDailyStatus,
    Employee,
    LeaveRecord,
    OvertimeConfig,
    PayrollAdjustment,
    PayrollRun,
    PayrollRunLine,
    PenaltyConfig,
)
from app.services.config_lookup import get_effective_config
from app.services.holiday_lookup import holiday_dates_in_range


def _period_bounds(year: int, month: int) -> tuple[date, date]:
    days_in_month = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, days_in_month)


def create_payroll_run(
    db: Session, period_year: int, period_month: int, location_id: int, generated_by_user_id: int
) -> PayrollRun:
    period_start, period_end = _period_bounds(period_year, period_month)
    days_in_month = period_end.day

    run = PayrollRun(
        location_id=location_id,
        period_year=period_year,
        period_month=period_month,
        status="draft",
        generated_by_user_id=generated_by_user_id,
    )
    db.add(run)
    db.flush()

    employees = db.execute(
        select(Employee).where(Employee.location_id == location_id, Employee.employment_status == "active")
    ).scalars().all()

    for emp in employees:
        line = _build_line(db, run.id, emp, period_start, period_end, days_in_month)
        db.add(line)

    db.flush()
    return run


def _build_line(db: Session, run_id: int, emp: Employee, period_start: date, period_end: date, days_in_month: int) -> PayrollRunLine:
    statuses = db.execute(
        select(AttendanceDailyStatus).where(
            AttendanceDailyStatus.employee_id == emp.id,
            AttendanceDailyStatus.work_date >= period_start,
            AttendanceDailyStatus.work_date <= period_end,
        )
    ).scalars().all()

    total_late_minutes = 0
    total_lateness_penalty = 0.0
    total_absence_days = 0.0
    total_absence_deduction = 0.0
    paid_leave_days = 0.0
    unpaid_leave_days = 0.0

    # overtime accumulation, split weekday/weekend, grouped by ISO week for
    # weekly-threshold apportionment
    weekly_buckets: dict[tuple[int, int], dict[str, int]] = {}

    # When the location's overtime config requires pre-approval, only days
    # somebody explicitly approved count toward pay. The minutes stay recorded
    # on the daily status either way, so an unapproved day is visible and can
    # be approved later and the run regenerated — it just never pays by
    # default. Read once per run from the period anchor, the same row
    # _overtime_bonus uses for rates and thresholds.
    anchor_ot_cfg = get_effective_config(db, OvertimeConfig, emp.location_id, period_start)
    overtime_needs_approval = bool(anchor_ot_cfg is not None and anchor_ot_cfg.requires_preapproval)

    # Public holidays in the period, resolved once (migration 0013). Work on
    # one is paid at the holiday rate rather than the weekday/weekend rate.
    holidays = holiday_dates_in_range(db, emp.location_id, period_start, period_end)

    for st in statuses:
        wd = st.work_date

        if st.late_minutes or st.early_departure_minutes or st.penalty_occurrences:
            total_late_minutes += st.late_minutes
            penalty_cfg = get_effective_config(db, PenaltyConfig, emp.location_id, wd)
            total_lateness_penalty += _lateness_penalty(
                penalty_cfg, st.late_minutes, st.early_departure_minutes, st.penalty_occurrences
            )

        if st.overtime_minutes and not (overtime_needs_approval and st.overtime_approved_at is None):
            iso_year, iso_week, _ = wd.isocalendar()
            bucket = weekly_buckets.setdefault(
                (iso_year, iso_week), {"weekday": 0, "weekend": 0, "holiday": 0}
            )
            if wd in holidays:
                key = "holiday"
            elif wd.weekday() >= 5:
                key = "weekend"
            else:
                key = "weekday"
            bucket[key] += st.overtime_minutes

        if st.status == "absent" and st.is_absence_excused is not True:
            total_absence_days += 1
            absence_cfg = get_effective_config(db, AbsenceRuleConfig, emp.location_id, wd)
            total_absence_deduction += _absence_deduction(absence_cfg, emp.base_salary_eur, days_in_month)

        if st.status == "on_leave":
            leave = db.execute(
                select(LeaveRecord).where(
                    LeaveRecord.employee_id == emp.id,
                    LeaveRecord.status == "approved",
                    LeaveRecord.start_date <= wd,
                    LeaveRecord.end_date >= wd,
                )
            ).scalars().first()
            is_paid = bool(leave and leave.leave_type and leave.leave_type.is_paid)
            if is_paid:
                paid_leave_days += 1
            else:
                unpaid_leave_days += 1

    total_overtime_minutes, overtime_bonus = _overtime_bonus(db, emp.location_id, period_start, weekly_buckets)

    net_pay = (
        float(emp.base_salary_eur)
        - total_lateness_penalty
        - total_absence_deduction
        + overtime_bonus
    )

    return PayrollRunLine(
        payroll_run_id=run_id,
        employee_id=emp.id,
        base_salary_eur=emp.base_salary_eur,
        total_late_minutes=total_late_minutes,
        total_lateness_penalty_eur=round(total_lateness_penalty, 2),
        total_overtime_minutes=total_overtime_minutes,
        total_overtime_bonus_eur=round(overtime_bonus, 2),
        total_absence_days=total_absence_days,
        total_absence_deduction_eur=round(total_absence_deduction, 2),
        paid_leave_days=paid_leave_days,
        unpaid_leave_days=unpaid_leave_days,
        net_pay_eur=round(net_pay, 2),
    )


def _lateness_penalty(
    cfg: PenaltyConfig | None,
    late_minutes: int,
    early_departure_minutes: int,
    penalty_occurrences: int = 0,
) -> float:
    if cfg is None:
        return 0.0

    # flat_per_occurrence: a flat amount for EACH chargeable event that day
    # (late to work, early from work, an over-long break — counted in
    # recompute.py as penalty_occurrences). This already covers early
    # departure and break, so it does NOT also add the per-minute early rate.
    if cfg.rule_type == "flat_per_occurrence":
        total = penalty_occurrences * float(cfg.flat_amount_eur or 0)
        if cfg.max_daily_penalty_eur is not None:
            total = min(total, float(cfg.max_daily_penalty_eur))
        return total

    lateness = 0.0
    if cfg.rule_type == "flat_per_minute":
        rate = float(cfg.rate_per_minute_eur or 0)
        lateness = late_minutes * rate
    elif cfg.rule_type == "threshold_allowance":
        allowance = cfg.allowance_minutes or 0
        if late_minutes > allowance:
            lateness = float(cfg.flat_amount_eur or 0)
    if cfg.max_daily_penalty_eur is not None:
        lateness = min(lateness, float(cfg.max_daily_penalty_eur))
    early_rate = float(cfg.early_departure_rate_per_minute_eur or 0)
    early_penalty = early_departure_minutes * early_rate
    return lateness + early_penalty


def _absence_deduction(cfg: AbsenceRuleConfig | None, base_salary_eur, days_in_month: int) -> float:
    if cfg is None:
        return 0.0
    if cfg.deduction_basis == "flat_amount":
        return float(cfg.deduction_value)
    # full_day_salary_fraction
    daily_rate = float(base_salary_eur) / days_in_month
    return daily_rate * float(cfg.deduction_value)


def _overtime_bonus(
    db: Session, location_id: int | None, period_anchor: date, weekly_buckets: dict[tuple[int, int], dict[str, int]]
) -> tuple[int, float]:
    if not weekly_buckets:
        return 0, 0.0

    ot_cfg = get_effective_config(db, OvertimeConfig, location_id, period_anchor)
    total_weekday = 0
    total_weekend = 0
    total_holiday = 0

    for (_, _), minutes in weekly_buckets.items():
        weekday_min = minutes["weekday"]
        weekend_min = minutes["weekend"]
        holiday_min = minutes.get("holiday", 0)
        week_total = weekday_min + weekend_min + holiday_min
        if ot_cfg is not None and ot_cfg.threshold_basis == "weekly" and week_total > 0:
            threshold = ot_cfg.weekly_threshold_minutes or 0
            adjusted_total = max(0, week_total - threshold)
            ratio = adjusted_total / week_total
            weekday_min = round(weekday_min * ratio)
            weekend_min = round(weekend_min * ratio)
            holiday_min = round(holiday_min * ratio)
        total_weekday += weekday_min
        total_weekend += weekend_min
        total_holiday += holiday_min

    total_minutes = total_weekday + total_weekend + total_holiday

    if ot_cfg is not None and ot_cfg.monthly_cap_minutes is not None and total_minutes > ot_cfg.monthly_cap_minutes:
        ratio = ot_cfg.monthly_cap_minutes / total_minutes if total_minutes else 0
        total_weekday = round(total_weekday * ratio)
        total_weekend = round(total_weekend * ratio)
        total_holiday = round(total_holiday * ratio)
        total_minutes = total_weekday + total_weekend + total_holiday

    if ot_cfg is None:
        return total_minutes, 0.0

    rate = float(ot_cfg.rate_per_hour_eur)
    weekend_rate = float(ot_cfg.weekend_rate_per_hour_eur) if ot_cfg.weekend_rate_per_hour_eur is not None else rate
    # Falls back to the ordinary rate, not the weekend one: an unset holiday
    # rate means "not configured", and silently paying holiday work at the
    # weekend premium would be inventing a policy nobody chose.
    holiday_rate = float(ot_cfg.holiday_rate_per_hour_eur) if ot_cfg.holiday_rate_per_hour_eur is not None else rate

    bonus = (
        (total_weekday / 60.0) * rate
        + (total_weekend / 60.0) * weekend_rate
        + (total_holiday / 60.0) * holiday_rate
    )
    return total_minutes, bonus


def recalculate_line_net_pay(db: Session, line: PayrollRunLine) -> None:
    adjustments = db.execute(
        select(PayrollAdjustment).where(PayrollAdjustment.payroll_run_line_id == line.id)
    ).scalars().all()
    adj_total = 0.0
    for a in adjustments:
        adj_total += float(a.amount_eur) if a.type == "bonus" else -float(a.amount_eur)

    base_net = (
        float(line.base_salary_eur)
        - float(line.total_lateness_penalty_eur)
        - float(line.total_absence_deduction_eur)
        + float(line.total_overtime_bonus_eur)
    )
    line.net_pay_eur = round(base_net + adj_total, 2)
