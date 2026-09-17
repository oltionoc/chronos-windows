"""Split shifts, parallel shift assignments, and overtime pre-approval.

Three features that arrived together (2026-09-17) and all touch payroll:

  * a weekday can hold SEVERAL work blocks (08:00-12:00 + 17:00-21:00), with
    late/early/overtime judged per block and summed;
  * an employee can hold several assignments covering the same dates, as long
    as the schedules behind them work different weekdays;
  * when `overtime_config.requires_preapproval` is set, overtime minutes are
    recorded but pay nothing until a specific day is approved.

Everything runs against the live stack over HTTP, like the rest of the suite.
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

MORNING = ("08:00:00", "12:00:00")
EVENING = ("17:00:00", "21:00:00")


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


def _split_days():
    """Mon-Fri as a split shift, weekend off."""
    return [
        {
            "day_of_week": dow,
            "is_working_day": True,
            "work_windows": [
                {"work_start_time": MORNING[0], "work_end_time": MORNING[1]},
                {"work_start_time": EVENING[0], "work_end_time": EVENING[1]},
            ],
            "break_windows": [],
        }
        for dow in range(5)
    ] + [{"day_of_week": dow, "is_working_day": False} for dow in (5, 6)]


@pytest.fixture(scope="module")
def split_world(admin_client: httpx.Client):
    """Own location so this module's overtime_config (which requires
    pre-approval) can't change what the shared `world` fixture's payroll
    assertions compute."""
    c = admin_client
    sfx = RUN_SUFFIX

    loc = c.post("/locations", json={"name": f"QA Loc SPLIT {sfx}", "timezone": "Europe/Tirane"}).json()

    sched = c.post(
        "/shift-schedules",
        json={"location_id": loc["id"], "name": f"QA Split Sched {sfx}", "grace_minutes_late": 0, "is_active": True},
    ).json()
    assert c.put(f"/shift-schedules/{sched['id']}/days", json={"days": _split_days()}).status_code == 200

    emp = c.post(
        "/employees",
        json={
            "location_id": loc["id"],
            "employee_code": f"SPLIT-{sfx}",
            "first_name": "QA",
            "last_name": "Split",
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
            "label": f"QA Split Device {sfx}",
            "ip_address": "10.0.0.240",
            "port": 4370,
            "is_active": True,
        },
    ).json()
    device_user = f"SPL{sfx}"[:20]
    assert (
        c.post(
            f"/employees/{emp['id']}/device-enrollments",
            json={"device_id": device["id"], "device_user_id": device_user},
        ).status_code
        == 201
    )

    # Overtime must be pre-approved at this location, and every minute past a
    # block's end counts (no daily threshold), so the approval tests can read
    # the arithmetic directly.
    c.post(
        "/config/overtime",
        json={
            "location_id": loc["id"],
            "threshold_basis": "daily",
            "daily_threshold_minutes": 0,
            "rate_per_hour_eur": 12.00,
            "requires_preapproval": True,
            "effective_from": "2025-01-01",
        },
    )

    monday = _recent_complete_work_week(date.today())
    return {
        "loc": loc,
        "schedule": sched,
        "employee": emp,
        "device": device,
        "device_user": device_user,
        "monday": monday,
    }


def _punch(split_world, day: date, hour: int, minute: int = 0):
    return {
        "device_id": split_world["device"]["id"],
        "device_user_id": split_world["device_user"],
        "punch_timestamp": _at(day, hour, minute),
        "raw_status_code": 0,
    }


def _status(admin_client, split_world, day: date) -> dict:
    r = admin_client.get(
        "/attendance/daily-status",
        params={
            "employee_id": split_world["employee"]["id"],
            "date_from": day.isoformat(),
            "date_to": day.isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, f"no daily status for {day}"
    return items[0]


# ---------------------------------------------------------------------------
# Split shift: two work blocks in one day
# ---------------------------------------------------------------------------

def test_split_shift_day_spans_both_blocks(admin_client, split_world):
    """Working both blocks exactly as scheduled is a clean day, and the stored
    scheduled_start/end are the day's OUTER bounds — the four-hour gap in the
    middle is not worked time and must not read as an early departure."""
    day = split_world["monday"]
    _ingest([
        _punch(split_world, day, 8, 0),
        _punch(split_world, day, 12, 0),
        _punch(split_world, day, 17, 0),
        _punch(split_world, day, 21, 0),
    ])
    st = _status(admin_client, split_world, day)
    assert st["scheduled_start"] == "08:00:00"
    assert st["scheduled_end"] == "21:00:00"
    assert st["late_minutes"] == 0
    assert st["early_departure_minutes"] == 0
    assert st["overtime_minutes"] == 0
    assert st["status"] == "present"


def test_split_shift_lateness_is_judged_per_block(admin_client, split_world):
    """Arriving on time in the morning but 30 minutes late to the evening
    block is 30 minutes late — measured against the EVENING block's start, not
    the day's."""
    day = split_world["monday"] + timedelta(days=1)
    _ingest([
        _punch(split_world, day, 8, 0),
        _punch(split_world, day, 12, 0),
        _punch(split_world, day, 17, 30),
        _punch(split_world, day, 21, 0),
    ])
    st = _status(admin_client, split_world, day)
    assert st["late_minutes"] == 30
    assert st["early_departure_minutes"] == 0
    assert st["status"] == "late"


def test_split_shift_early_departure_and_overtime_sum_across_blocks(admin_client, split_world):
    """Leaving the morning block 30 minutes early and staying 45 past the
    evening block: both are real, both are counted, and neither cancels the
    other out."""
    day = split_world["monday"] + timedelta(days=2)
    _ingest([
        _punch(split_world, day, 8, 0),
        _punch(split_world, day, 11, 30),
        _punch(split_world, day, 17, 0),
        _punch(split_world, day, 21, 45),
    ])
    st = _status(admin_client, split_world, day)
    assert st["early_departure_minutes"] == 30
    assert st["overtime_minutes"] == 45
    assert st["late_minutes"] == 0


def test_work_blocks_may_not_overlap(admin_client, split_world):
    days = _split_days()
    days[0]["work_windows"] = [
        {"work_start_time": "08:00:00", "work_end_time": "13:00:00"},
        {"work_start_time": "12:00:00", "work_end_time": "16:00:00"},
    ]
    r = admin_client.put(f"/shift-schedules/{split_world['schedule']['id']}/days", json={"days": days})
    assert r.status_code == 400, r.text

    # The rejected write must not have wiped the schedule it was replacing.
    schedule = admin_client.get(f"/shift-schedules/{split_world['schedule']['id']}").json()
    monday = next(d for d in schedule["days"] if d["day_of_week"] == 0)
    assert len(monday["work_windows"]) == 2
    assert monday["work_start_time"] == "08:00:00"


# ---------------------------------------------------------------------------
# Parallel assignments: two schedules, different weekdays, same dates
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def parallel_world(admin_client: httpx.Client, split_world):
    """One employee holding two open-ended assignments at once: a Mon-Tue
    schedule and a Wed-Fri one."""
    c = admin_client
    sfx = RUN_SUFFIX
    loc_id = split_world["loc"]["id"]

    def make_schedule(name: str, working: set[int], start: str, end: str):
        sched = c.post(
            "/shift-schedules",
            json={"location_id": loc_id, "name": f"{name} {sfx}", "grace_minutes_late": 0, "is_active": True},
        ).json()
        days = [
            {
                "day_of_week": dow,
                "is_working_day": dow in working,
                "work_start_time": start if dow in working else None,
                "work_end_time": end if dow in working else None,
                "break_windows": [],
            }
            for dow in range(7)
        ]
        assert c.put(f"/shift-schedules/{sched['id']}/days", json={"days": days}).status_code == 200
        return sched

    early = make_schedule("QA Par Early", {0, 1}, "06:00:00", "14:00:00")
    late = make_schedule("QA Par Late", {2, 3, 4}, "14:00:00", "22:00:00")

    emp = c.post(
        "/employees",
        json={
            "location_id": loc_id,
            "employee_code": f"PAR-{sfx}",
            "first_name": "QA",
            "last_name": "Parallel",
            "hire_date": "2025-01-01",
            "base_salary_eur": 1000.00,
            "employment_status": "active",
        },
    ).json()
    return {"employee": emp, "early": early, "late": late, "loc_id": loc_id}


def test_two_schedules_can_cover_the_same_dates_on_different_days(admin_client, parallel_world):
    emp_id = parallel_world["employee"]["id"]
    for sched in (parallel_world["early"], parallel_world["late"]):
        r = admin_client.post(
            f"/employees/{emp_id}/shift-assignments",
            json={"shift_schedule_id": sched["id"], "effective_from": "2025-01-01"},
        )
        assert r.status_code == 201, r.text
    assert len(admin_client.get(f"/employees/{emp_id}/shift-assignments").json()) == 2


def test_a_third_schedule_claiming_a_taken_weekday_is_rejected(admin_client, parallel_world, split_world):
    """The relaxed rule still has to refuse genuine ambiguity: the split
    schedule works Mon-Fri, which collides with both assignments above."""
    r = admin_client.post(
        f"/employees/{parallel_world['employee']['id']}/shift-assignments",
        json={"shift_schedule_id": split_world["schedule"]["id"], "effective_from": "2025-01-01"},
    )
    assert r.status_code == 409, r.text


def test_each_weekday_is_computed_against_its_own_schedule(admin_client, parallel_world, split_world):
    """Monday belongs to the 06:00-14:00 schedule and Wednesday to the
    14:00-22:00 one, even though both assignments are open-ended and cover
    both dates."""
    monday = split_world["monday"]
    wednesday = monday + timedelta(days=2)

    r = admin_client.post(
        "/attendance/recompute",
        json={
            "date_from": monday.isoformat(),
            "date_to": wednesday.isoformat(),
            "employee_id": parallel_world["employee"]["id"],
        },
    )
    assert r.status_code == 204, r.text

    rows = admin_client.get(
        "/attendance/daily-status",
        params={
            "employee_id": parallel_world["employee"]["id"],
            "date_from": monday.isoformat(),
            "date_to": wednesday.isoformat(),
        },
    ).json()["items"]
    by_date = {row["work_date"]: row for row in rows}
    assert by_date[monday.isoformat()]["scheduled_start"] == "06:00:00"
    assert by_date[monday.isoformat()]["scheduled_end"] == "14:00:00"
    assert by_date[wednesday.isoformat()]["scheduled_start"] == "14:00:00"
    assert by_date[wednesday.isoformat()]["scheduled_end"] == "22:00:00"


# ---------------------------------------------------------------------------
# Overtime pre-approval
# ---------------------------------------------------------------------------

def _run_payroll(admin_client, split_world) -> dict:
    monday = split_world["monday"]
    r = admin_client.post(
        "/payroll/runs",
        json={"period_year": monday.year, "period_month": monday.month, "location_id": split_world["loc"]["id"]},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    line = admin_client.get(f"/payroll/runs/{run['id']}/lines/{split_world['employee']['id']}").json()
    assert admin_client.delete(f"/payroll/runs/{run['id']}").status_code == 204
    return line


def test_unapproved_overtime_is_recorded_but_not_paid(admin_client, split_world):
    """45 minutes of real overtime exist on the day (see the split-shift test
    above) and the config requires pre-approval, so payroll pays nothing for
    them yet."""
    day = split_world["monday"] + timedelta(days=2)
    st = _status(admin_client, split_world, day)
    assert st["overtime_minutes"] == 45
    assert st["overtime_requires_approval"] is True
    assert st["overtime_approved_at"] is None

    line = _run_payroll(admin_client, split_world)
    assert line["total_overtime_minutes"] == 0
    assert line["total_overtime_bonus_eur"] == pytest.approx(0.0)


def test_approving_the_day_makes_the_same_overtime_payable(admin_client, split_world):
    day = split_world["monday"] + timedelta(days=2)
    st = _status(admin_client, split_world, day)

    r = admin_client.patch(f"/attendance/daily-status/{st['id']}/overtime-approval", json={"approved": True})
    assert r.status_code == 200, r.text
    assert r.json()["overtime_approved_at"] is not None

    line = _run_payroll(admin_client, split_world)
    assert line["total_overtime_minutes"] == 45
    # 45 min at 12.00/hr
    assert line["total_overtime_bonus_eur"] == pytest.approx(9.00)


def test_approval_is_cleared_when_the_overtime_figure_changes(admin_client, split_world):
    """An approval covers the number of minutes the approver saw. A later
    punch that changes that number voids it, rather than silently paying out
    a figure nobody approved."""
    day = split_world["monday"] + timedelta(days=2)
    st = _status(admin_client, split_world, day)
    assert st["overtime_approved_at"] is not None, "previous test should have left this approved"

    # A pair, not a single punch: punches are classified by alternating
    # parity, so one extra punch would be read as a dangling check-IN and the
    # day's last check-out (and therefore its overtime) would not move at all.
    _ingest([_punch(split_world, day, 22, 15), _punch(split_world, day, 22, 45)])

    st_after = _status(admin_client, split_world, day)
    assert st_after["overtime_minutes"] > 45
    assert st_after["overtime_approved_at"] is None

    line = _run_payroll(admin_client, split_world)
    assert line["total_overtime_minutes"] == 0


# ---------------------------------------------------------------------------
# Alert: punched outside the schedule
# ---------------------------------------------------------------------------

def test_punch_outside_schedule_alert(admin_client, split_world):
    """Two things must be flagged and neither may change pay by itself: a
    punch in the middle of the night on a working day, and a punch on a day
    the employee isn't scheduled at all."""
    workday = split_world["monday"] + timedelta(days=3)
    saturday = split_world["monday"] + timedelta(days=5)
    assert saturday.weekday() == 5

    _ingest([
        _punch(split_world, workday, 8, 0),
        _punch(split_world, workday, 3, 10),
        _punch(split_world, saturday, 10, 0),
    ])

    alerts = admin_client.get("/reports/alerts", params={"days": 30, "location_id": split_world["loc"]["id"]}).json()["alerts"]
    outside = [
        a
        for a in alerts
        if a["type"] == "punch_outside_schedule" and a["employee_id"] == split_world["employee"]["id"]
    ]
    flagged_dates = {a["work_date"] for a in outside}
    assert workday.isoformat() in flagged_dates
    assert saturday.isoformat() in flagged_dates

    # The 08:00 punch on the working day is inside the schedule and must not
    # be counted in that day's alert.
    workday_alert = next(a for a in outside if a["work_date"] == workday.isoformat())
    assert workday_alert["count"] == 1

    # Saturday still pays nothing on its own — flagging it is the whole point.
    st = _status(admin_client, split_world, saturday)
    assert st["status"] == "not_scheduled"
    assert st["overtime_minutes"] == 0


def test_overtime_pending_approval_alert(admin_client, split_world):
    day = split_world["monday"] + timedelta(days=2)
    st = _status(admin_client, split_world, day)
    assert st["overtime_minutes"] > 0 and st["overtime_approved_at"] is None

    alerts = admin_client.get("/reports/alerts", params={"days": 30, "location_id": split_world["loc"]["id"]}).json()["alerts"]
    pending = [
        a
        for a in alerts
        if a["type"] == "overtime_pending_approval" and a["employee_id"] == split_world["employee"]["id"]
    ]
    assert pending, "overtime awaiting approval should be surfaced as an alert"
    assert pending[0]["work_date"] == day.isoformat()
