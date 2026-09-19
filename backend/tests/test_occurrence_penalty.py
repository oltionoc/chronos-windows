"""Flat-per-occurrence penalties, including break violations (client req 11).

The client charges a flat amount (e.g. 5 EUR) for EACH chargeable event in a
day — late to work, early from work, and a break that ran long — not per
minute and not once per day. Break violations were not penalised at all
before.

`penalty_occurrences` on the daily status counts the events; payroll multiplies
it by the flat amount. Verified over the live stack.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from conftest import API_BASE_URL, RUN_SUFFIX, _compose_exec_python, _recent_complete_work_week

INTERNAL_API_KEY = _compose_exec_python("from app.config import settings; print(settings.internal_api_key)")
TZ = ZoneInfo("Europe/Tirane")
FLAT = 5.0


def _ingest(punches):
    r = httpx.post(f"{API_BASE_URL}/internal/ingest/punches", json={"punches": punches},
                   headers={"X-Internal-Key": INTERNAL_API_KEY}, timeout=20)
    assert r.status_code == 200, r.text


def _at(day, h, m=0):
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ).isoformat()


@pytest.fixture(scope="module")
def occ_world(admin_client: httpx.Client):
    c = admin_client
    sfx = RUN_SUFFIX
    loc = c.post("/locations", json={"name": f"QA Loc OCC {sfx}", "timezone": "Europe/Tirane"}).json()
    sched = c.post("/shift-schedules", json={"location_id": loc["id"], "name": f"QA Occ {sfx}",
                                             "grace_minutes_late": 5, "is_active": True}).json()
    # 09:00-17:00 with a 12:00-12:30 break (30 min allowed).
    days = [
        {"day_of_week": dow, "is_working_day": True, "work_start_time": "09:00:00", "work_end_time": "17:00:00",
         "break_windows": [{"break_start_time": "12:00:00", "break_end_time": "12:30:00", "is_paid": False}]}
        for dow in range(7)
    ]
    c.put(f"/shift-schedules/{sched['id']}/days", json={"days": days})
    emp = c.post("/employees", json={"location_id": loc["id"], "employee_code": f"OCC-{sfx}", "first_name": "QA",
                                     "last_name": "Occ", "hire_date": "2025-01-01", "base_salary_eur": 1000.0,
                                     "employment_status": "active"}).json()
    c.post(f"/employees/{emp['id']}/shift-assignments", json={"shift_schedule_id": sched["id"], "effective_from": "2025-01-01"})
    device = c.post("/devices", json={"location_id": loc["id"], "label": f"QA Occ Dev {sfx}", "ip_address": "10.0.0.61",
                                      "port": 4370, "is_active": True}).json()
    uid = f"OCC{sfx}"[:20]
    c.post(f"/employees/{emp['id']}/device-enrollments", json={"device_id": device["id"], "device_user_id": uid})
    # flat_per_occurrence at 5 EUR.
    c.post("/config/penalty", json={"location_id": loc["id"], "rule_type": "flat_per_occurrence",
                                    "flat_amount_eur": FLAT, "effective_from": "2025-01-01"})
    return {"loc": loc, "emp": emp, "device": device, "user": uid, "monday": _recent_complete_work_week(date.today())}


def _status(admin_client, world, day):
    rows = admin_client.get("/attendance/daily-status",
                            params={"employee_id": world["emp"]["id"], "date_from": day.isoformat(), "date_to": day.isoformat()}).json()["items"]
    assert rows, f"no status for {day}"
    return rows[0]


def _punch(world, day, h, m, code=0):
    # code 0 = inferred work; 2 = break-out, 3 = break-in (the device's break
    # buttons), which classify regardless of the exact minute — needed when a
    # long break means returning after the break window has closed.
    return {"device_id": world["device"]["id"], "device_user_id": world["user"], "punch_timestamp": _at(day, h, m), "raw_status_code": code}


def test_on_time_full_day_no_occurrences(admin_client, occ_world):
    day = occ_world["monday"]
    _ingest([_punch(occ_world, day, 9, 0), _punch(occ_world, day, 12, 0, 2), _punch(occ_world, day, 12, 30, 3), _punch(occ_world, day, 17, 0)])
    st = _status(admin_client, occ_world, day)
    assert st["penalty_occurrences"] == 0


def test_late_to_work_is_one_occurrence(admin_client, occ_world):
    day = occ_world["monday"] + timedelta(days=1)
    _ingest([_punch(occ_world, day, 9, 20), _punch(occ_world, day, 17, 0)])
    st = _status(admin_client, occ_world, day)
    assert st["late_minutes"] == 15  # 09:20 vs 09:00+5 grace
    assert st["penalty_occurrences"] == 1


def test_long_break_is_one_occurrence_even_when_on_time(admin_client, occ_world):
    """Returned from a 30-min break after 45 min (well past 30 + 5 grace).
    On time in and out, but the break alone is a chargeable event — which the
    old system never penalised."""
    day = occ_world["monday"] + timedelta(days=2)
    _ingest([_punch(occ_world, day, 9, 0), _punch(occ_world, day, 12, 0, 2), _punch(occ_world, day, 12, 45, 3), _punch(occ_world, day, 17, 0)])
    st = _status(admin_client, occ_world, day)
    assert st["late_minutes"] == 0
    assert st["break_minutes_taken"] == 45
    assert st["penalty_occurrences"] == 1


def test_late_and_early_and_long_break_is_three(admin_client, occ_world):
    day = occ_world["monday"] + timedelta(days=3)
    # late in (09:20), long break (12:00-12:50 = 50 min), early out (16:30)
    _ingest([_punch(occ_world, day, 9, 20), _punch(occ_world, day, 12, 0, 2), _punch(occ_world, day, 12, 50, 3), _punch(occ_world, day, 16, 30)])
    st = _status(admin_client, occ_world, day)
    assert st["penalty_occurrences"] == 3


def test_payroll_charges_flat_amount_per_occurrence(admin_client, occ_world):
    day = occ_world["monday"]
    r = admin_client.post("/payroll/runs",
                          json={"period_year": day.year, "period_month": day.month, "location_id": occ_world["loc"]["id"]})
    assert r.status_code == 201, r.text
    run = r.json()
    line = admin_client.get(f"/payroll/runs/{run['id']}/lines/{occ_world['emp']['id']}").json()
    # Days set up this month for this employee: Mon 0 occ, Tue 1, Wed 1, Thu 3 = 5 occurrences total.
    assert line["total_lateness_penalty_eur"] == pytest.approx(5 * FLAT)
    assert admin_client.delete(f"/payroll/runs/{run['id']}").status_code == 204
