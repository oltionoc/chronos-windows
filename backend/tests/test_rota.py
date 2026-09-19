"""Per-date rota — shift templates assigned to an employee per specific date.

The client's staff rotate freely (morning one day, afternoon the next), so a
shift is assigned per DATE, not per weekday. A rota entry overrides the weekly
schedule for its date; with no entry, the weekly schedule still applies.

These tests prove: the rota drives lateness/overtime against the assigned
template, a day off suppresses the working day, and clearing an entry falls
back to the weekly schedule. All against the live stack over HTTP.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from conftest import API_BASE_URL, RUN_SUFFIX, _compose_exec_python

INTERNAL_API_KEY = _compose_exec_python("from app.config import settings; print(settings.internal_api_key)")
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


def _monday(offset_weeks: int = 1) -> date:
    d = date.today() - timedelta(days=date.today().weekday() + 7 * offset_weeks)
    return d


@pytest.fixture(scope="module")
def rota_world(admin_client: httpx.Client):
    c = admin_client
    sfx = RUN_SUFFIX
    loc = c.post("/locations", json={"name": f"QA Loc ROTA {sfx}", "timezone": "Europe/Tirane"}).json()

    # A weekly schedule that works Mon-Fri 09-17 — the fallback the rota overrides.
    sched = c.post(
        "/shift-schedules",
        json={"location_id": loc["id"], "name": f"QA Weekly {sfx}", "grace_minutes_late": 5, "is_active": True},
    ).json()
    days = [
        {"day_of_week": dow, "is_working_day": dow < 5, "work_start_time": "09:00:00" if dow < 5 else None,
         "work_end_time": "17:00:00" if dow < 5 else None, "break_windows": []}
        for dow in range(7)
    ]
    c.put(f"/shift-schedules/{sched['id']}/days", json={"days": days})

    emp = c.post(
        "/employees",
        json={"location_id": loc["id"], "employee_code": f"ROTA-{sfx}", "first_name": "QA", "last_name": "Rota",
              "hire_date": "2025-01-01", "base_salary_eur": 1000.0, "employment_status": "active"},
    ).json()
    c.post(f"/employees/{emp['id']}/shift-assignments", json={"shift_schedule_id": sched["id"], "effective_from": "2025-01-01"})

    device = c.post(
        "/devices",
        json={"location_id": loc["id"], "label": f"QA Rota Dev {sfx}", "ip_address": "10.0.0.60", "port": 4370, "is_active": True},
    ).json()
    uid = f"ROTA{sfx}"[:20]
    c.post(f"/employees/{emp['id']}/device-enrollments", json={"device_id": device["id"], "device_user_id": uid})

    morning = c.post(
        "/shift-templates",
        json={"location_id": loc["id"], "name": f"Paradite {sfx}", "work_start_time": "10:00:00",
              "work_end_time": "18:00:00", "break_start_time": "13:00:00", "break_end_time": "13:30:00",
              "grace_minutes_late": 5},
    ).json()
    afternoon = c.post(
        "/shift-templates",
        json={"location_id": loc["id"], "name": f"Pasdite {sfx}", "work_start_time": "14:00:00",
              "work_end_time": "22:00:00", "grace_minutes_late": 5},
    ).json()

    return {"loc": loc, "sched": sched, "emp": emp, "device": device, "user": uid,
            "morning": morning, "afternoon": afternoon, "monday": _monday()}


def _recompute(admin_client, emp_id, day):
    r = admin_client.post("/attendance/recompute",
                          json={"date_from": day.isoformat(), "date_to": day.isoformat(), "employee_id": emp_id})
    assert r.status_code == 204, r.text


def _status(admin_client, emp_id, day):
    rows = admin_client.get("/attendance/daily-status",
                            params={"employee_id": emp_id, "date_from": day.isoformat(), "date_to": day.isoformat()}).json()["items"]
    assert rows, f"no status for {day}"
    return rows[0]


def _set_rota(admin_client, emp_id, day, template_id=None, clear=False):
    r = admin_client.put("/rota", json={"entries": [
        {"employee_id": emp_id, "work_date": day.isoformat(), "shift_template_id": template_id, "clear": clear}
    ]})
    assert r.status_code == 204, r.text


def test_rota_grid_lists_the_week(admin_client, rota_world):
    r = admin_client.get("/rota", params={"location_id": rota_world["loc"]["id"], "week_start": rota_world["monday"].isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["dates"]) == 7
    assert any(e["employee_id"] == rota_world["emp"]["id"] for e in body["employees"])


def test_afternoon_shift_on_a_date_drives_lateness_against_that_shift(admin_client, rota_world):
    """Monday's weekly schedule is 09-17, but the rota puts this employee on the
    14-22 afternoon shift. Arriving 14:20 is 15 min late against 14:00 (+5
    grace), NOT hours early against 09:00."""
    day = rota_world["monday"]
    _set_rota(admin_client, rota_world["emp"]["id"], day, rota_world["afternoon"]["id"])
    _ingest([
        {"device_id": rota_world["device"]["id"], "device_user_id": rota_world["user"], "punch_timestamp": _at(day, 14, 20), "raw_status_code": 0},
        {"device_id": rota_world["device"]["id"], "device_user_id": rota_world["user"], "punch_timestamp": _at(day, 22, 0), "raw_status_code": 0},
    ])
    st = _status(admin_client, rota_world["emp"]["id"], day)
    assert st["scheduled_start"] == "14:00:00"
    assert st["scheduled_end"] == "22:00:00"
    assert st["late_minutes"] == 15
    assert st["early_departure_minutes"] == 0
    assert st["status"] == "late"


def test_next_day_the_same_employee_can_be_on_the_morning_shift(admin_client, rota_world):
    """The whole point of a rota: different shift the next day."""
    day = rota_world["monday"] + timedelta(days=1)
    _set_rota(admin_client, rota_world["emp"]["id"], day, rota_world["morning"]["id"])
    _ingest([
        {"device_id": rota_world["device"]["id"], "device_user_id": rota_world["user"], "punch_timestamp": _at(day, 10, 0), "raw_status_code": 0},
        {"device_id": rota_world["device"]["id"], "device_user_id": rota_world["user"], "punch_timestamp": _at(day, 18, 0), "raw_status_code": 0},
    ])
    st = _status(admin_client, rota_world["emp"]["id"], day)
    assert st["scheduled_start"] == "10:00:00"
    assert st["scheduled_end"] == "18:00:00"
    assert st["late_minutes"] == 0
    assert st["status"] == "present"


def test_a_rota_day_off_overrides_a_weekly_working_day(admin_client, rota_world):
    """Wednesday is a working day in the weekly schedule; a NULL-template rota
    entry makes it a day off, so no lateness even with no punches."""
    day = rota_world["monday"] + timedelta(days=2)
    _set_rota(admin_client, rota_world["emp"]["id"], day, template_id=None)
    _recompute(admin_client, rota_world["emp"]["id"], day)
    st = _status(admin_client, rota_world["emp"]["id"], day)
    assert st["status"] == "not_scheduled"


def test_clearing_a_rota_entry_falls_back_to_the_weekly_schedule(admin_client, rota_world):
    """Thursday: put a rota shift, then clear it — the weekly 09-17 applies
    again."""
    day = rota_world["monday"] + timedelta(days=3)
    _set_rota(admin_client, rota_world["emp"]["id"], day, rota_world["afternoon"]["id"])
    st = _status(admin_client, rota_world["emp"]["id"], day) if False else None  # no recompute yet
    _set_rota(admin_client, rota_world["emp"]["id"], day, clear=True)
    _recompute(admin_client, rota_world["emp"]["id"], day)
    st = _status(admin_client, rota_world["emp"]["id"], day)
    # Back to the weekly schedule's outer bounds.
    assert st["scheduled_start"] == "09:00:00"
    assert st["scheduled_end"] == "17:00:00"


def test_a_template_in_use_cannot_be_deleted(admin_client, rota_world):
    r = admin_client.delete(f"/shift-templates/{rota_world['afternoon']['id']}")
    assert r.status_code == 409, r.text


def test_break_inside_a_rota_template_is_recognised(admin_client, rota_world):
    """The morning template has a 13:00-13:30 break; punches there are break,
    not work, so break minutes are counted."""
    day = rota_world["monday"] + timedelta(days=4)
    _set_rota(admin_client, rota_world["emp"]["id"], day, rota_world["morning"]["id"])
    d, uid = rota_world["device"]["id"], rota_world["user"]
    _ingest([
        {"device_id": d, "device_user_id": uid, "punch_timestamp": _at(day, 10, 0), "raw_status_code": 0},
        {"device_id": d, "device_user_id": uid, "punch_timestamp": _at(day, 13, 0), "raw_status_code": 0},
        {"device_id": d, "device_user_id": uid, "punch_timestamp": _at(day, 13, 30), "raw_status_code": 0},
        {"device_id": d, "device_user_id": uid, "punch_timestamp": _at(day, 18, 0), "raw_status_code": 0},
    ])
    st = _status(admin_client, rota_world["emp"]["id"], day)
    assert st["break_minutes_taken"] == 30
    assert st["late_minutes"] == 0
    assert st["early_departure_minutes"] == 0
