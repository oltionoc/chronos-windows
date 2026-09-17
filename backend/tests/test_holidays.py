"""Public holiday calendar — migration 0013, services/holiday_lookup.py.

`attendance_daily_status.status` has allowed 'holiday' since the first
migration and `overtime_config.holiday_rate_per_hour_eur` has existed just as
long, but nothing could set either until this table existed. The two things
that were actually wrong every year, at every location, and which these tests
pin down:

  * an absence deduction taken from someone who was correctly off;
  * holiday work paid at the ordinary rate.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from conftest import API_BASE_URL, RUN_SUFFIX, _compose_exec_python, _recent_complete_work_week

INTERNAL_API_KEY = _compose_exec_python(
    "from app.config import settings; print(settings.internal_api_key)"
)
TZ = ZoneInfo("Europe/Tirane")


def _ingest(punches):
    r = httpx.post(
        f"{API_BASE_URL}/internal/ingest/punches",
        json={"punches": punches},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
        timeout=20,
    )
    assert r.status_code == 200, r.text


def _at(day: date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).isoformat()


@pytest.fixture(scope="module")
def holiday_world(admin_client: httpx.Client):
    """Own location, so the holiday calendar and overtime rates here cannot
    change what the shared `world` fixture's payroll assertions compute."""
    c = admin_client
    sfx = RUN_SUFFIX

    loc = c.post("/locations", json={"name": f"QA Loc HOL {sfx}", "timezone": "Europe/Tirane"}).json()
    sched = c.post(
        "/shift-schedules",
        json={"location_id": loc["id"], "name": f"QA Hol Sched {sfx}", "grace_minutes_late": 0, "is_active": True},
    ).json()
    days = [
        {
            "day_of_week": dow,
            "is_working_day": dow < 5,
            "work_start_time": "09:00:00" if dow < 5 else None,
            "work_end_time": "17:00:00" if dow < 5 else None,
            "break_windows": [],
        }
        for dow in range(7)
    ]
    assert c.put(f"/shift-schedules/{sched['id']}/days", json={"days": days}).status_code == 200

    def make_employee(code: str):
        emp = c.post(
            "/employees",
            json={
                "location_id": loc["id"],
                "employee_code": f"{code}-{sfx}",
                "first_name": "QA",
                "last_name": code,
                "hire_date": "2025-01-01",
                "base_salary_eur": 1200.00,
                "employment_status": "active",
            },
        ).json()
        c.post(
            f"/employees/{emp['id']}/shift-assignments",
            json={"shift_schedule_id": sched["id"], "effective_from": "2025-01-01"},
        )
        return emp

    worker = make_employee("HolWork")   # works the holiday
    absentee = make_employee("HolOff")  # stays home, as intended

    device = c.post(
        "/devices",
        json={
            "location_id": loc["id"],
            "label": f"QA Hol Device {sfx}",
            "ip_address": "10.0.0.250",
            "port": 4370,
            "is_active": True,
        },
    ).json()
    device_user = f"HOL{sfx}"[:20]
    c.post(
        f"/employees/{worker['id']}/device-enrollments",
        json={"device_id": device["id"], "device_user_id": device_user},
    )

    # Absence deduction must exist, otherwise "no deduction on a holiday"
    # would pass for the wrong reason.
    c.post(
        "/config/absence-rule",
        json={
            "location_id": loc["id"],
            "rule_type": "unexcused_absence",
            "deduction_basis": "full_day_salary_fraction",
            "deduction_value": 1.0,
            "effective_from": "2025-01-01",
        },
    )
    c.post(
        "/config/overtime",
        json={
            "location_id": loc["id"],
            "threshold_basis": "daily",
            "daily_threshold_minutes": 0,
            "rate_per_hour_eur": 10.00,
            "holiday_rate_per_hour_eur": 30.00,
            "effective_from": "2025-01-01",
        },
    )

    monday = _recent_complete_work_week(date.today())
    return {
        "loc": loc,
        "schedule": sched,
        "worker": worker,
        "absentee": absentee,
        "device": device,
        "device_user": device_user,
        "monday": monday,
    }


def _recompute(admin_client, employee_id, day: date):
    r = admin_client.post(
        "/attendance/recompute",
        json={"date_from": day.isoformat(), "date_to": day.isoformat(), "employee_id": employee_id},
    )
    assert r.status_code == 204, r.text


def _status(admin_client, employee_id, day: date) -> dict:
    rows = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": employee_id, "date_from": day.isoformat(), "date_to": day.isoformat()},
    ).json()["items"]
    assert rows, f"no daily status for {day}"
    return rows[0]


@pytest.fixture(scope="module")
def declared_holiday(admin_client, holiday_world):
    """Tuesday of the reference week declared a holiday at this location."""
    day = holiday_world["monday"] + timedelta(days=1)
    r = admin_client.post(
        "/holidays",
        json={
            "location_id": holiday_world["loc"]["id"],
            "holiday_date": day.isoformat(),
            "name_en": f"QA Holiday {RUN_SUFFIX}",
            "name_sq": f"QA Festë {RUN_SUFFIX}",
            "recurs_annually": False,
        },
    )
    assert r.status_code == 201, r.text
    return {"day": day, "row": r.json()}


# ---------------------------------------------------------------------------
# The calendar itself
# ---------------------------------------------------------------------------

def test_two_holidays_cannot_share_a_date_in_the_same_scope(admin_client, holiday_world, declared_holiday):
    r = admin_client.post(
        "/holidays",
        json={
            "location_id": holiday_world["loc"]["id"],
            "holiday_date": declared_holiday["day"].isoformat(),
            "name_en": "Duplicate",
            "name_sq": "Dublikat",
        },
    )
    assert r.status_code == 409, r.text


def test_a_manager_cannot_create_an_org_wide_holiday(world):
    """Org-wide changes every location's payroll, so it stays admin-only —
    the same rule the config endpoints use."""
    r = world["mgr_a"].post(
        "/holidays",
        json={
            "location_id": None,
            "holiday_date": "2031-01-01",
            "name_en": "Sneaky Global",
            "name_sq": "Globale",
        },
    )
    assert r.status_code == 403, r.text


def test_recurring_holidays_are_listed_for_every_year(admin_client, holiday_world):
    created = admin_client.post(
        "/holidays",
        json={
            "location_id": holiday_world["loc"]["id"],
            "holiday_date": "2026-01-01",
            "name_en": f"QA New Year {RUN_SUFFIX}",
            "name_sq": f"QA Viti i Ri {RUN_SUFFIX}",
            "recurs_annually": True,
        },
    )
    assert created.status_code == 201, created.text
    for year in (2026, 2027, 2030):
        rows = admin_client.get("/holidays", params={"year": year, "location_id": holiday_world["loc"]["id"]}).json()
        assert any(h["id"] == created.json()["id"] for h in rows), f"missing from {year}"
    admin_client.delete(f"/holidays/{created.json()['id']}")


# ---------------------------------------------------------------------------
# What it does to attendance
# ---------------------------------------------------------------------------

def test_nobody_is_marked_absent_on_a_holiday(admin_client, holiday_world, declared_holiday):
    """The headline bug: a public holiday used to read as an unexcused
    absence for everyone who was correctly at home, and deduct a day's pay."""
    day = declared_holiday["day"]
    _recompute(admin_client, holiday_world["absentee"]["id"], day)
    st = _status(admin_client, holiday_world["absentee"]["id"], day)
    assert st["status"] == "holiday"
    assert st["late_minutes"] == 0
    assert st["overtime_minutes"] == 0


def test_working_a_holiday_records_the_hours_as_holiday_work(admin_client, holiday_world, declared_holiday):
    day = declared_holiday["day"]
    d, uid = holiday_world["device"], holiday_world["device_user"]
    _ingest([
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _at(day, 9), "raw_status_code": 0},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _at(day, 13), "raw_status_code": 0},
    ])
    st = _status(admin_client, holiday_world["worker"]["id"], day)
    assert st["status"] == "holiday"
    assert st["overtime_minutes"] == 240
    assert st["late_minutes"] == 0, "nobody can be late to a day they were not scheduled for"


def test_leave_covering_a_holiday_does_not_consume_a_leave_day(admin_client, holiday_world, declared_holiday):
    """A public holiday inside annual leave is a holiday, not a leave day —
    which is why the holiday check runs before the leave check."""
    day = declared_holiday["day"]
    leave_type = admin_client.post(
        "/leave-types",
        json={
            "name_en": f"QA Hol Leave {RUN_SUFFIX}",
            "name_sq": f"QA Leje Feste {RUN_SUFFIX}",
            "is_paid": True,
            "requires_approval": False,
            "is_active": True,
        },
    ).json()
    record = admin_client.post(
        "/leave-records",
        json={
            "employee_id": holiday_world["absentee"]["id"],
            "leave_type_id": leave_type["id"],
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
        },
    )
    assert record.status_code == 201, record.text

    _recompute(admin_client, holiday_world["absentee"]["id"], day)
    assert _status(admin_client, holiday_world["absentee"]["id"], day)["status"] == "holiday"


# ---------------------------------------------------------------------------
# What it does to payroll
# ---------------------------------------------------------------------------

def test_holiday_work_is_paid_at_the_holiday_rate(admin_client, holiday_world, declared_holiday):
    """4h worked on the holiday. Ordinary overtime is 10.00/h, the holiday
    rate is 30.00/h — 40.00 vs 120.00 is the difference this feature exists
    to stop getting wrong."""
    day = declared_holiday["day"]
    r = admin_client.post(
        "/payroll/runs",
        json={"period_year": day.year, "period_month": day.month, "location_id": holiday_world["loc"]["id"]},
    )
    assert r.status_code == 201, r.text
    run = r.json()

    worker_line = admin_client.get(f"/payroll/runs/{run['id']}/lines/{holiday_world['worker']['id']}").json()
    assert worker_line["total_overtime_minutes"] == 240
    assert worker_line["total_overtime_bonus_eur"] == pytest.approx(120.00)

    absentee_line = admin_client.get(f"/payroll/runs/{run['id']}/lines/{holiday_world['absentee']['id']}").json()
    assert absentee_line["total_absence_days"] == 0.0, "a holiday is not an absence"
    assert absentee_line["total_absence_deduction_eur"] == pytest.approx(0.0)
    assert absentee_line["paid_leave_days"] == 0.0, "and it does not spend a leave day either"

    assert admin_client.delete(f"/payroll/runs/{run['id']}").status_code == 204
