"""Break punch semantics — the canon documented in services/classify.py.

`check_out_break` is punching OUT for a break (chronologically first),
`check_in_break` is punching back IN (second). Three independent paths can
produce a break pair, and all three must agree, because they feed the same
`break_minutes_taken` subtraction in services/recompute.py:

  1. a vendor that labels its own events  (Hikvision -> punch_type_hint)
  2. a vendor that emits raw break codes  (ZKTeco   -> raw_status_code 2/3)
  3. no vendor signal at all              (inferred from the schedule's
                                           break window + punch order)

Regression origin: (1) and (2) used to label the pair one way while the
inferred path (3) and the recompute subtraction used the opposite order. The
two inversions cancelled for (3), so break minutes looked correct in testing,
but any device supplying a real break code silently contributed **0 minutes**
— no error, just a wrong number reaching payroll. Each test below asserts
both the labels and a non-zero duration, so a re-inversion anywhere fails
loudly.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from conftest import API_BASE_URL, RUN_SUFFIX, _compose_exec_python

INTERNAL_API_KEY = _compose_exec_python(
    "from app.config import settings; print(settings.internal_api_key)"
)
TZ = ZoneInfo("Europe/Tirane")
BREAK_MINUTES = 30


def _ingest(punches):
    r = httpx.post(
        f"{API_BASE_URL}/internal/ingest/punches",
        json={"punches": punches},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
        timeout=20,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _local(day: date, hour: int, minute: int) -> str:
    """UTC instant for a wall-clock time at the location, so the break window
    comparison (which is done in the employee's own timezone) is exercised
    rather than accidentally bypassed."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=TZ).isoformat()


def _workday(index: int) -> date:
    """The `index`-th most recent Mon-Fri before today, counting back.

    Each test needs its OWN working day: punches are deduped and accumulated
    per employee-day, so two tests sharing a date would recompute against the
    union of both their punches. Walking back by calendar offset and snapping
    weekends onto the preceding Friday does NOT give distinct days (offsets
    4, 5 and 6 from a Thursday all land on the same Friday), so count working
    days directly."""
    d = date.today()
    remaining = index + 1
    while remaining:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            remaining -= 1
    return d


@pytest.fixture(scope="module")
def break_world(admin_client: httpx.Client, world):
    """A schedule carrying a real 12:00-13:00 break window, one employee on
    it, and that employee enrolled on both a Hikvision device (can supply
    hints) and a ZKTeco one (cannot)."""
    c = admin_client
    sfx = RUN_SUFFIX
    loc_id = world["loc_a"]["id"]

    sched = c.post(
        "/shift-schedules",
        json={"location_id": loc_id, "name": f"QA Break Sched {sfx}", "grace_minutes_late": 5, "is_active": True},
    ).json()
    days = [
        {
            "day_of_week": dow,
            "is_working_day": dow < 5,
            "work_start_time": "09:00:00" if dow < 5 else None,
            "work_end_time": "17:00:00" if dow < 5 else None,
            "break_windows": (
                [{"break_start_time": "12:00:00", "break_end_time": "13:00:00", "is_paid": False}] if dow < 5 else []
            ),
        }
        for dow in range(7)
    ]
    assert c.put(f"/shift-schedules/{sched['id']}/days", json={"days": days}).status_code == 200

    emp = c.post(
        "/employees",
        json={
            "location_id": loc_id,
            "employee_code": f"BRK-{sfx}",
            "first_name": "QA",
            "last_name": "Break",
            "hire_date": "2025-01-01",
            "base_salary_eur": 1000.00,
            "employment_status": "active",
        },
    ).json()
    c.post(
        f"/employees/{emp['id']}/shift-assignments",
        json={"shift_schedule_id": sched["id"], "effective_from": "2025-01-01"},
    )

    hik = c.post(
        "/devices",
        json={
            "location_id": loc_id,
            "label": f"QA Brk Hik {sfx}",
            "device_type": "hikvision",
            "ip_address": "10.0.0.231",
            "port": 80,
            "auth_username": "admin",
            "auth_password": "DevicePw123",
            "is_active": True,
        },
    ).json()
    zk = c.post(
        "/devices",
        json={
            "location_id": loc_id,
            "label": f"QA Brk ZK {sfx}",
            "device_type": "zkteco",
            "ip_address": "10.0.0.232",
            "port": 4370,
            "is_active": True,
        },
    ).json()
    for dev, uid in ((hik, f"BRKH{sfx}"[:20]), (zk, f"BRKZ{sfx}"[:20])):
        assert (
            c.post(
                f"/employees/{emp['id']}/device-enrollments",
                json={"device_id": dev["id"], "device_user_id": uid},
            ).status_code
            == 201
        )

    return {
        "employee": emp,
        "hik": hik,
        "hik_user": f"BRKH{sfx}"[:20],
        "zk": zk,
        "zk_user": f"BRKZ{sfx}"[:20],
    }


def _day_status(admin_client, employee_id, day: date):
    r = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": employee_id, "date_from": day.isoformat(), "date_to": day.isoformat()},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, f"no daily status computed for {day}"
    return items[0]


def _punch_types(admin_client, employee_id, day: date):
    r = admin_client.get(
        "/attendance/logs",
        params={"employee_id": employee_id, "date_from": day.isoformat(), "date_to": day.isoformat(), "page_size": 50},
    )
    assert r.status_code == 200, r.text
    rows = sorted(r.json()["items"], key=lambda x: x["punch_timestamp"])
    return [x["punch_type"] for x in rows]


def test_device_labelled_break_counts_minutes(admin_client, break_world):
    """Path 1: the device classifies its own events. The pair must come back
    as departure-then-return and produce real minutes — this is the case that
    silently yielded 0 before the canon was settled."""
    day = _workday(0)
    d, uid = break_world["hik"], break_world["hik_user"]
    _ingest([
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 9, 0), "raw_status_code": 0, "punch_type_hint": "check_in_work"},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 12, 0), "raw_status_code": 2, "punch_type_hint": "check_out_break"},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 12, BREAK_MINUTES), "raw_status_code": 3, "punch_type_hint": "check_in_break"},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 17, 0), "raw_status_code": 1, "punch_type_hint": "check_out_work"},
    ])

    assert _punch_types(admin_client, break_world["employee"]["id"], day) == [
        "check_in_work", "check_out_break", "check_in_break", "check_out_work",
    ]
    assert _day_status(admin_client, break_world["employee"]["id"], day)["break_minutes_taken"] == BREAK_MINUTES


def test_raw_break_codes_count_minutes(admin_client, break_world):
    """Path 2: ZKTeco supplies no hint, only raw status codes 2 (out) and 3
    (in), which classify.py maps directly."""
    day = _workday(1)
    d, uid = break_world["zk"], break_world["zk_user"]
    _ingest([
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 9, 0), "raw_status_code": 0},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 12, 0), "raw_status_code": 2},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 12, BREAK_MINUTES), "raw_status_code": 3},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 17, 0), "raw_status_code": 1},
    ])

    assert _punch_types(admin_client, break_world["employee"]["id"], day) == [
        "check_in_work", "check_out_break", "check_in_break", "check_out_work",
    ]
    assert _day_status(admin_client, break_world["employee"]["id"], day)["break_minutes_taken"] == BREAK_MINUTES


def test_inferred_break_counts_minutes(admin_client, break_world):
    """Path 3: no vendor signal at all — the device reports a bare code 0 for
    every punch (what a Hikvision with attendance mode off actually does).
    Break-ness comes purely from the punch falling inside the schedule's
    break window, and order from position within that window."""
    day = _workday(2)
    d, uid = break_world["zk"], break_world["zk_user"]
    _ingest([
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 9, 0), "raw_status_code": 0},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 12, 5), "raw_status_code": 0},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 12, 5 + BREAK_MINUTES), "raw_status_code": 0},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 17, 0), "raw_status_code": 0},
    ])

    assert _punch_types(admin_client, break_world["employee"]["id"], day) == [
        "check_in_work", "check_out_break", "check_in_break", "check_out_work",
    ]
    assert _day_status(admin_client, break_world["employee"]["id"], day)["break_minutes_taken"] == BREAK_MINUTES


def test_departure_without_return_reads_as_on_break_not_negative(admin_client, break_world):
    """A break that was never returned from must not produce negative or
    phantom minutes — reports.py treats an unreturned check_out_break as
    "on break", and recompute must simply not pair it."""
    day = _workday(3)
    d, uid = break_world["zk"], break_world["zk_user"]
    _ingest([
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 9, 0), "raw_status_code": 0},
        {"device_id": d["id"], "device_user_id": uid, "punch_timestamp": _local(day, 12, 0), "raw_status_code": 2},
    ])
    assert _day_status(admin_client, break_world["employee"]["id"], day)["break_minutes_taken"] == 0
