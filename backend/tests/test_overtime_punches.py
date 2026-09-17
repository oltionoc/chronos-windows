"""Explicitly badged overtime — migration 0014.

Both vendors can label a punch as overtime (Hikvision `overtimeIn`/
`overtimeOut`, ZKTeco punch codes 4/5). Those punches used to be folded into
ordinary check-in/check-out, so the device's own statement "this stretch was
overtime" was thrown away and overtime was only ever inferred from the
schedule.

The rule these tests pin down: overtime the employee BADGED is exempt from
the daily overtime threshold, while overtime merely INFERRED from staying
late still goes through it. The threshold exists to ignore drifting past the
end of a shift; pressing the overtime key is not drift. Pre-approval still
gates whether any of it is paid.
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
DAILY_THRESHOLD_MINUTES = 30


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
def ot_world(admin_client: httpx.Client):
    c = admin_client
    sfx = RUN_SUFFIX

    loc = c.post("/locations", json={"name": f"QA Loc OT {sfx}", "timezone": "Europe/Tirane"}).json()
    sched = c.post(
        "/shift-schedules",
        json={"location_id": loc["id"], "name": f"QA OT Sched {sfx}", "grace_minutes_late": 0, "is_active": True},
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

    # A real daily threshold, so "exempt" and "not exempt" produce visibly
    # different numbers rather than both being zero-subtracted.
    c.post(
        "/config/overtime",
        json={
            "location_id": loc["id"],
            "threshold_basis": "daily",
            "daily_threshold_minutes": DAILY_THRESHOLD_MINUTES,
            "rate_per_hour_eur": 10.00,
            "effective_from": "2025-01-01",
        },
    )

    def make(code: str, device_type: str, ip: str, port: int):
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
        device = c.post(
            "/devices",
            json={
                "location_id": loc["id"],
                "label": f"QA OT {code} {sfx}",
                "device_type": device_type,
                "ip_address": ip,
                "port": port,
                **({"auth_username": "admin", "auth_password": "DevicePw123"} if device_type != "zkteco" else {}),
                "is_active": True,
            },
        ).json()
        uid = f"{code}{sfx}"[:20]
        assert (
            c.post(
                f"/employees/{emp['id']}/device-enrollments",
                json={"device_id": device["id"], "device_user_id": uid},
            ).status_code
            == 201
        )
        return {"employee": emp, "device": device, "user": uid}

    return {
        "loc": loc,
        # Hikvision labels its own events, so this one arrives with hints.
        "hik": make("OTH", "hikvision", "10.0.0.251", 80),
        # ZKTeco sends only raw codes 4/5.
        "zk": make("OTZ", "zkteco", "10.0.0.252", 4370),
        "monday": _recent_complete_work_week(date.today()),
    }


def _punch(who, day: date, hour: int, minute: int, code: int, hint: str | None = None):
    body = {
        "device_id": who["device"]["id"],
        "device_user_id": who["user"],
        "punch_timestamp": _at(day, hour, minute),
        "raw_status_code": code,
    }
    if hint is not None:
        body["punch_type_hint"] = hint
    return body


def _status(admin_client, who, day: date) -> dict:
    rows = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": who["employee"]["id"], "date_from": day.isoformat(), "date_to": day.isoformat()},
    ).json()["items"]
    assert rows, f"no daily status for {day}"
    return rows[0]


def _punch_types(admin_client, who, day: date):
    rows = admin_client.get(
        "/attendance/logs",
        params={
            "employee_id": who["employee"]["id"],
            "date_from": day.isoformat(),
            "date_to": day.isoformat(),
            "page_size": 50,
        },
    ).json()["items"]
    return [r["punch_type"] for r in sorted(rows, key=lambda r: r["punch_timestamp"])]


def test_hikvision_overtime_events_are_stored_as_overtime(admin_client, ot_world):
    """The device said overtimeIn/overtimeOut; that must survive into the log
    instead of being flattened into an ordinary check-in/check-out."""
    day = ot_world["monday"]
    who = ot_world["hik"]
    _ingest([
        _punch(who, day, 9, 0, 0, "check_in_work"),
        _punch(who, day, 17, 0, 1, "check_out_work"),
        _punch(who, day, 17, 30, 4, "check_in_overtime"),
        _punch(who, day, 19, 30, 5, "check_out_overtime"),
    ])
    assert _punch_types(admin_client, who, day) == [
        "check_in_work", "check_out_work", "check_in_overtime", "check_out_overtime",
    ]


def test_badged_overtime_skips_the_daily_threshold(admin_client, ot_world):
    """120 minutes badged, and all 120 are payable — the 30-minute threshold
    is for ignoring drift, and deliberately clocking overtime is not drift."""
    day = ot_world["monday"]
    st = _status(admin_client, ot_world["hik"], day)
    assert st["overtime_minutes"] == 120
    assert st["late_minutes"] == 0
    assert st["early_departure_minutes"] == 0, "clocking out at 17:00 is not an early departure"


def test_inferred_overtime_still_goes_through_the_threshold(admin_client, ot_world):
    """Same two hours, but nobody badged anything: they just stayed late. That
    is the case the threshold exists for, so 30 minutes come off."""
    day = ot_world["monday"] + timedelta(days=1)
    who = ot_world["zk"]
    _ingest([
        _punch(who, day, 9, 0, 0),
        _punch(who, day, 19, 0, 1),
    ])
    st = _status(admin_client, who, day)
    assert st["overtime_minutes"] == 120 - DAILY_THRESHOLD_MINUTES


def test_zkteco_raw_codes_4_and_5_are_read_as_overtime(admin_client, ot_world):
    """No hint, no schedule inference — only the vendor's punch codes."""
    day = ot_world["monday"] + timedelta(days=2)
    who = ot_world["zk"]
    _ingest([
        _punch(who, day, 9, 0, 0),
        _punch(who, day, 17, 0, 1),
        _punch(who, day, 18, 0, 4),
        _punch(who, day, 19, 0, 5),
    ])
    assert _punch_types(admin_client, who, day) == [
        "check_in_work", "check_out_work", "check_in_overtime", "check_out_overtime",
    ]
    assert _status(admin_client, who, day)["overtime_minutes"] == 60


def test_badged_and_inferred_overtime_add_up(admin_client, ot_world):
    """Stayed 60 minutes past the shift AND badged an hour later on. Both are
    real, each is treated by its own rule: 60 - 30 threshold, plus 60 exempt."""
    day = ot_world["monday"] + timedelta(days=3)
    who = ot_world["zk"]
    _ingest([
        _punch(who, day, 9, 0, 0),
        _punch(who, day, 18, 0, 1),
        _punch(who, day, 20, 0, 4),
        _punch(who, day, 21, 0, 5),
    ])
    assert _status(admin_client, who, day)["overtime_minutes"] == (60 - DAILY_THRESHOLD_MINUTES) + 60


def test_an_unclosed_overtime_punch_pays_nothing(admin_client, ot_world):
    """A forgotten "end overtime" must not run to the end of the day and
    invent hours — same rule as a forgotten check-out."""
    day = ot_world["monday"] + timedelta(days=4)
    who = ot_world["zk"]
    _ingest([
        _punch(who, day, 9, 0, 0),
        _punch(who, day, 17, 0, 1),
        _punch(who, day, 18, 0, 4),
    ])
    assert _status(admin_client, who, day)["overtime_minutes"] == 0


def test_overtime_only_day_is_not_an_absence(admin_client, ot_world):
    """Came in solely to work overtime on a scheduled day. They were at work,
    so they are not absent, but nothing about the shift they never worked can
    make them late."""
    day = ot_world["monday"] + timedelta(days=1)
    who = ot_world["hik"]
    _ingest([
        _punch(who, day, 19, 0, 4, "check_in_overtime"),
        _punch(who, day, 21, 0, 5, "check_out_overtime"),
    ])
    st = _status(admin_client, who, day)
    assert st["status"] != "absent"
    assert st["late_minutes"] == 0
    assert st["early_departure_minutes"] == 0
    assert st["overtime_minutes"] == 120


def test_badged_overtime_is_paid_at_the_overtime_rate(admin_client, ot_world):
    day = ot_world["monday"]
    r = admin_client.post(
        "/payroll/runs",
        json={"period_year": day.year, "period_month": day.month, "location_id": ot_world["loc"]["id"]},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    line = admin_client.get(f"/payroll/runs/{run['id']}/lines/{ot_world['hik']['employee']['id']}").json()
    # 120 badged (Mon) + 120 badged (Tue overtime-only day) = 240 min at 10.00/h
    assert line["total_overtime_minutes"] == 240
    assert line["total_overtime_bonus_eur"] == pytest.approx(40.00)
    assert admin_client.delete(f"/payroll/runs/{run['id']}").status_code == 204
