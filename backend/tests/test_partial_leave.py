"""Partial-day (hourly) leave — a permission window inside a working day
(client req: staff who take a few hours off with a return, or leave/arrive on
approved permission) must NOT be penalised for lateness, early departure, or a
long break that the permission covers. A full-day leave (no times) still turns
the whole day into on_leave.

All against the live stack over HTTP.
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
def leave_world(admin_client: httpx.Client):
    c = admin_client
    sfx = RUN_SUFFIX
    loc = c.post("/locations", json={"name": f"QA Loc LV {sfx}", "timezone": "Europe/Tirane"}).json()
    sched = c.post("/shift-schedules", json={"location_id": loc["id"], "name": f"QA LV {sfx}",
                                             "grace_minutes_late": 5, "is_active": True}).json()
    days = [
        {"day_of_week": dow, "is_working_day": True, "work_start_time": "09:00:00", "work_end_time": "17:00:00",
         "break_windows": [{"break_start_time": "12:00:00", "break_end_time": "12:30:00", "is_paid": False}]}
        for dow in range(7)
    ]
    c.put(f"/shift-schedules/{sched['id']}/days", json={"days": days})
    emp = c.post("/employees", json={"location_id": loc["id"], "employee_code": f"LV-{sfx}", "first_name": "QA",
                                     "last_name": "Leave", "hire_date": "2025-01-01", "base_salary_eur": 1000.0,
                                     "employment_status": "active"}).json()
    c.post(f"/employees/{emp['id']}/shift-assignments", json={"shift_schedule_id": sched["id"], "effective_from": "2025-01-01"})
    device = c.post("/devices", json={"location_id": loc["id"], "label": f"QA LV Dev {sfx}", "ip_address": "10.0.0.62",
                                      "port": 4370, "is_active": True}).json()
    uid = f"LV{sfx}"[:20]
    c.post(f"/employees/{emp['id']}/device-enrollments", json={"device_id": device["id"], "device_user_id": uid})
    c.post("/config/penalty", json={"location_id": loc["id"], "rule_type": "flat_per_occurrence",
                                    "flat_amount_eur": FLAT, "effective_from": "2025-01-01"})
    lt = c.post("/leave-types", json={"name_en": f"Permission {sfx}", "name_sq": f"Leje {sfx}",
                                      "is_paid": True, "requires_approval": False, "is_active": True}).json()
    return {"loc": loc, "emp": emp, "device": device, "user": uid, "lt": lt,
            "monday": _recent_complete_work_week(date.today())}


def _punch(world, day, h, m, code=0):
    return {"device_id": world["device"]["id"], "device_user_id": world["user"],
            "punch_timestamp": _at(day, h, m), "raw_status_code": code}


def _status(admin_client, world, day):
    rows = admin_client.get("/attendance/daily-status",
                            params={"employee_id": world["emp"]["id"], "date_from": day.isoformat(),
                                    "date_to": day.isoformat()}).json()["items"]
    assert rows, f"no status for {day}"
    return rows[0]


def _leave(admin_client, world, day, start_time=None, end_time=None, end_day=None):
    return admin_client.post("/leave-records", json={
        "employee_id": world["emp"]["id"], "leave_type_id": world["lt"]["id"],
        "start_date": day.isoformat(), "end_date": (end_day or day).isoformat(),
        "start_time": start_time, "end_time": end_time,
    })


def test_late_arrival_without_leave_is_penalised(admin_client, leave_world):
    """Control: 09:30 arrival, no permission — one late occurrence."""
    day = leave_world["monday"]
    _ingest([_punch(leave_world, day, 9, 30), _punch(leave_world, day, 17, 0)])
    st = _status(admin_client, leave_world, day)
    assert st["late_minutes"] == 25  # 09:30 vs 09:00 + 5 grace
    assert st["penalty_occurrences"] == 1


def test_permission_covering_the_start_excuses_lateness(admin_client, leave_world):
    """Same 09:30 arrival, but a 09:00-10:00 permission — no lateness, no
    occurrence. Recompute runs on leave creation."""
    day = leave_world["monday"] + timedelta(days=1)
    _ingest([_punch(leave_world, day, 9, 30), _punch(leave_world, day, 17, 0)])
    assert _leave(admin_client, leave_world, day, "09:00:00", "10:00:00").status_code == 201
    st = _status(admin_client, leave_world, day)
    assert st["late_minutes"] == 0
    assert st["penalty_occurrences"] == 0


def test_permission_covering_the_end_excuses_early_departure(admin_client, leave_world):
    day = leave_world["monday"] + timedelta(days=2)
    _ingest([_punch(leave_world, day, 9, 0), _punch(leave_world, day, 16, 0)])
    assert _leave(admin_client, leave_world, day, "15:30:00", "17:00:00").status_code == 201
    st = _status(admin_client, leave_world, day)
    assert st["early_departure_minutes"] == 0
    assert st["penalty_occurrences"] == 0


def test_full_day_leave_still_makes_the_day_on_leave(admin_client, leave_world):
    """No times = the whole day is leave, takes precedence over any punches."""
    day = leave_world["monday"] + timedelta(days=3)
    _ingest([_punch(leave_world, day, 9, 40), _punch(leave_world, day, 17, 0)])
    assert _leave(admin_client, leave_world, day).status_code == 201
    st = _status(admin_client, leave_world, day)
    assert st["status"] == "on_leave"


def test_partial_leave_needs_both_times(admin_client, leave_world):
    day = leave_world["monday"] + timedelta(days=4)
    r = _leave(admin_client, leave_world, day, start_time="09:00:00")  # no end_time
    assert r.status_code == 400, r.text


def test_partial_leave_must_be_a_single_day(admin_client, leave_world):
    day = leave_world["monday"] + timedelta(days=4)
    r = _leave(admin_client, leave_world, day, "09:00:00", "10:00:00", end_day=day + timedelta(days=1))
    assert r.status_code == 400, r.text
