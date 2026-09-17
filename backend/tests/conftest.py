"""Shared fixtures for the QA end-to-end smoke suite.

These tests exercise the REAL running `docker compose` stack over HTTP (no
mocks, no in-process TestClient) — per this project's established convention
(BACKEND_NOTES.md Section 1: "verified end-to-end against a real PostgreSQL
instance"). They assume `docker compose up` is already running with the `api`
service reachable at `API_BASE_URL` (default http://localhost:8000/api/v1)
and the `docker compose` CLI reachable from wherever pytest runs (used only
to bootstrap/teardown a throwaway `admin` test account directly in the DB,
the same way this project's build/QA sessions have always done it — there is
no other way to get valid credentials without knowing the real admin
password, which QA is explicitly not given).

Run with:
    cd backend
    python -m venv .venv && source .venv/bin/activate  # or use any Python 3.11+
    pip install -r requirements-dev.txt
    pytest tests/ -v
"""
import secrets
import subprocess
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

API_BASE_URL = "http://localhost:8000/api/v1"

# Unique per test-session suffix so re-running the suite never collides with
# a previous (interrupted) run's leftover data, and so teardown can find
# exactly (and only) what this run created.
RUN_SUFFIX = secrets.token_hex(4)


def _compose_exec_python(code: str) -> str:
    """Run a Python one-liner inside the live `api` container — same
    mechanism this project's build/security/QA passes have always used to
    get DB access without a published Postgres port."""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "python", "-c", code],
        cwd="/home/olti/web-agency/chronos-testing-env/chronos",
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker compose exec failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


@pytest.fixture(scope="session")
def qa_username():
    return f"qa_pytest_{RUN_SUFFIX}"


@pytest.fixture(scope="session")
def qa_password():
    return "QaPytest123!"


@pytest.fixture(scope="session")
def admin_client(qa_username, qa_password):
    """A logged-in httpx.Client authenticated as a throwaway admin user,
    created directly in the DB (bootstrap problem: QA has no real admin
    credentials — see module docstring). Cleaned up at session end.

    The login and the yield sit inside try/finally: setup can fail *after*
    the account row exists (auth.py rate-limits per account, so a burst of
    bad logins elsewhere locks this one out), and without the finally that
    account was orphaned in the database with no suffix left to find it by.
    """
    _compose_exec_python(
        f"""
from app.database import SessionLocal
from app.models import User
from app.security import hash_password
db = SessionLocal()
u = User(username={qa_username!r}, password_hash=hash_password({qa_password!r}),
         role='admin', is_active=True, must_change_password=False)
db.add(u)
db.commit()
print(u.id)
db.close()
"""
    )

    client = httpx.Client(base_url=API_BASE_URL, timeout=15)
    try:
        resp = client.post("/auth/login", json={"username": qa_username, "password": qa_password})
        assert resp.status_code == 204, resp.text
        yield client
    finally:
        _teardown(client)


def _teardown(client):
    client.close()
    # Teardown: remove every row this test session created, in FK-safe
    # order. Direct SQL rather than API calls, because several domain
    # entities have no DELETE endpoint by design (employees, locations,
    # shift schedules — see BLUEPRINT.md: history/audit rows are meant to be
    # immutable, not because it's an oversight), and a finalized payroll run
    # is deliberately undeletable (SECURITY_REPORT.md finding 27). Test
    # cleanup is not a business operation, so bypassing those guards here
    # (for rows this same run created, identified by RUN_SUFFIX) is safe and
    # doesn't touch anything else in the DB.
    _compose_exec_python(
        f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
suffix = {RUN_SUFFIX!r}
like = f'%{{suffix}}%'
db.execute(text("DELETE FROM payroll_adjustments WHERE payroll_run_line_id IN (SELECT prl.id FROM payroll_run_lines prl JOIN employees e ON e.id = prl.employee_id WHERE e.employee_code LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM payroll_run_lines WHERE employee_id IN (SELECT id FROM employees WHERE employee_code LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM payroll_runs WHERE id NOT IN (SELECT payroll_run_id FROM payroll_run_lines) AND generated_by_user_id IN (SELECT id FROM users WHERE username LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM leave_records WHERE employee_id IN (SELECT id FROM employees WHERE employee_code LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM attendance_daily_status WHERE employee_id IN (SELECT id FROM employees WHERE employee_code LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM attendance_logs WHERE employee_id IN (SELECT id FROM employees WHERE employee_code LIKE :p)"), {{"p": like}})
# Punches ingested for a device_user_id that was never enrolled land with
# employee_id NULL (the multi-vendor punch_type_hint tests do exactly
# this), so they are only reachable through the device.
db.execute(text("DELETE FROM attendance_logs WHERE device_id IN (SELECT id FROM devices WHERE label LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM employee_device_enrollments WHERE employee_id IN (SELECT id FROM employees WHERE employee_code LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM employee_device_enrollments WHERE device_id IN (SELECT id FROM devices WHERE label LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM employee_shift_assignments WHERE employee_id IN (SELECT id FROM employees WHERE employee_code LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM employees WHERE employee_code LIKE :p"), {{"p": like}})
db.execute(text("DELETE FROM devices WHERE label LIKE :p"), {{"p": like}})
db.execute(text("DELETE FROM shift_break_windows WHERE shift_schedule_day_id IN (SELECT ssd.id FROM shift_schedule_days ssd JOIN shift_schedules ss ON ss.id = ssd.shift_schedule_id WHERE ss.name LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM shift_schedule_days WHERE shift_schedule_id IN (SELECT id FROM shift_schedules WHERE name LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM shift_schedules WHERE name LIKE :p"), {{"p": like}})
db.execute(text("DELETE FROM holidays WHERE location_id IN (SELECT id FROM locations WHERE name LIKE :p) OR name_en LIKE :p"), {{"p": like}})
db.execute(text("DELETE FROM penalty_config WHERE location_id IN (SELECT id FROM locations WHERE name LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM overtime_config WHERE location_id IN (SELECT id FROM locations WHERE name LIKE :p)"), {{"p": like}})
db.execute(text("DELETE FROM absence_rule_config WHERE location_id IN (SELECT id FROM locations WHERE name LIKE :p)"), {{"p": like}})
# leave_types.name was split into name_en/name_sq by migration
# 0007_leave_type_bilingual_name; this teardown still keyed off the old
# column and threw, which aborted the whole transaction and left every
# other DELETE above uncommitted.
db.execute(text("DELETE FROM leave_types WHERE name_en LIKE :p"), {{"p": like}})
db.execute(text("DELETE FROM users WHERE username LIKE :p"), {{"p": like}})
db.execute(text("DELETE FROM locations WHERE name LIKE :p"), {{"p": like}})
db.commit()
db.close()
"""
    )


INTERNAL_API_KEY = _compose_exec_python(
    "from app.config import settings; print(settings.internal_api_key)"
)


def _recent_complete_work_week(today: date) -> date:
    """Monday of the most recent Mon-Fri that is entirely in the past AND
    entirely inside one calendar month.

    Both constraints matter:
      * fully elapsed — the fixture asserts on a finished week (an absence on
        Wednesday, an early departure on Friday); a future day has no punches
        and no daily-status row.
      * single month — the payroll-run assertions build one run for
        `monday`'s year/month and expect the whole week's totals in it.

    The result is at most 20 days old, so it stays inside the 30-day
    /reports/alerts window this suite queries with.
    """
    monday = today - timedelta(days=today.weekday() + 7)  # last week's Monday
    if (monday + timedelta(days=4)).month != monday.month:
        monday -= timedelta(days=7)
    return monday


# ---------------------------------------------------------------------------
# World fixture — builds the shared scenario once per session:
#   - two locations, one shift schedule each (Mon-Fri 09:00-17:00, 5min grace)
#   - one manager per location (location-scoped access)
#   - one plain employee per location (for scoping tests)
#   - one "payroll" employee at location A with a realistic attendance week:
#       Mon: late beyond grace       -> late_minutes > 0
#       Tue: on-time in, late out    -> overtime_minutes > 0 (daily threshold)
#       Wed: no punches               -> absent, deduction applied
#       Thu: check-in only, no out   -> missing_checkout, NOT early departure
#       Fri: on-time in, early out   -> early_departure_minutes > 0
#   - penalty_config (threshold_allowance) + overtime_config (daily) at loc A
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def world(admin_client: httpx.Client):
    c = admin_client
    sfx = RUN_SUFFIX

    loc_a = c.post("/locations", json={"name": f"QA Loc A {sfx}", "timezone": "Europe/Tirane"}).json()
    loc_b = c.post("/locations", json={"name": f"QA Loc B {sfx}", "timezone": "Europe/Tirane"}).json()

    def make_schedule(location_id):
        sched = c.post(
            "/shift-schedules",
            json={"location_id": location_id, "name": f"QA Sched {sfx} L{location_id}", "grace_minutes_late": 5, "is_active": True},
        ).json()
        days = [
            {"day_of_week": dow, "is_working_day": True, "work_start_time": "09:00:00", "work_end_time": "17:00:00", "break_windows": []}
            for dow in range(5)
        ] + [
            {"day_of_week": dow, "is_working_day": False} for dow in (5, 6)
        ]
        r = c.put(f"/shift-schedules/{sched['id']}/days", json={"days": days})
        assert r.status_code == 200, r.text
        return sched

    sched_a = make_schedule(loc_a["id"])
    sched_b = make_schedule(loc_b["id"])

    def make_employee(code, location_id, salary=1000.00):
        emp = c.post(
            "/employees",
            json={
                "location_id": location_id,
                "employee_code": f"{code}-{sfx}",
                "first_name": "QA",
                "last_name": code,
                "hire_date": "2025-01-01",
                "base_salary_eur": salary,
                "employment_status": "active",
            },
        ).json()
        return emp

    emp_a = make_employee("EmpA", loc_a["id"])
    emp_b = make_employee("EmpB", loc_b["id"])
    payroll_emp = make_employee("Payroll", loc_a["id"], salary=1200.00)

    c.post("/employees/%d/shift-assignments" % emp_a["id"], json={"shift_schedule_id": sched_a["id"], "effective_from": "2025-01-01"})
    c.post("/employees/%d/shift-assignments" % emp_b["id"], json={"shift_schedule_id": sched_b["id"], "effective_from": "2025-01-01"})
    c.post("/employees/%d/shift-assignments" % payroll_emp["id"], json={"shift_schedule_id": sched_a["id"], "effective_from": "2025-01-01"})

    device = c.post(
        "/devices",
        json={"location_id": loc_a["id"], "label": f"QA Device {sfx}", "ip_address": "10.0.0.199", "port": 4370, "is_active": True},
    ).json()
    c.post(f"/employees/{payroll_emp['id']}/device-enrollments", json={"device_id": device["id"], "device_user_id": "QAPAY"})

    # Managers (must-change-password gate: HR-created accounts always start
    # with must_change_password=True — SECURITY_REPORT.md finding 1 — so we
    # log in and change it before using the client for scoped calls).
    def make_manager(username, location_id, pw):
        c.post("/users", json={"username": username, "password": pw, "role": "manager", "location_id": location_id})
        mc = httpx.Client(base_url=API_BASE_URL, timeout=15)
        r = mc.post("/auth/login", json={"username": username, "password": pw})
        assert r.status_code == 204, r.text
        new_pw = pw + "New1"
        r = mc.patch("/auth/me/password", json={"current_password": pw, "new_password": new_pw})
        assert r.status_code == 204, r.text
        return mc

    mgr_a = make_manager(f"qa_mgr_a_{sfx}", loc_a["id"], "MgrAPass1!")
    mgr_b = make_manager(f"qa_mgr_b_{sfx}", loc_b["id"], "MgrBPass1!")

    # Configs (location A only)
    penalty_cfg = c.post(
        "/config/penalty",
        json={
            "location_id": loc_a["id"],
            "rule_type": "threshold_allowance",
            "allowance_minutes": 10,
            "flat_amount_eur": 15.00,
            "max_daily_penalty_eur": 50.00,
            "early_departure_rate_per_minute_eur": 0.20,
            "effective_from": "2026-01-01",
        },
    ).json()
    overtime_cfg = c.post(
        "/config/overtime",
        json={
            "location_id": loc_a["id"],
            "threshold_basis": "daily",
            "daily_threshold_minutes": 30,
            "rate_per_hour_eur": 10.00,
            "effective_from": "2026-01-01",
        },
    ).json()

    # Attendance week: a recent, fully-elapsed Mon-Fri.
    #
    # This used to be a hard-coded `date(2026, 8, 10)`, which silently rotted:
    # once "today" moved more than 30 days past it, every assertion that reads
    # /reports/alerts (a `days`-windowed endpoint) stopped matching, and the
    # payroll-run month drifted away from the current one. Deriving it from
    # `today` keeps the week inside every relative window for good.
    tz = ZoneInfo("Europe/Tirane")
    monday = _recent_complete_work_week(datetime.now(tz).date())

    def utc_iso(d: date, h: int, m: int) -> str:
        return datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(ZoneInfo("UTC")).isoformat()

    punches = [
        # Mon: late in (09:20 vs 09:00+5min grace), on-time out
        {"punch_timestamp": utc_iso(monday, 9, 20), "raw_status_code": 0},
        {"punch_timestamp": utc_iso(monday, 17, 0), "raw_status_code": 1},
        # Tue: on-time in, late out -> overtime
        {"punch_timestamp": utc_iso(monday + timedelta(days=1), 9, 0), "raw_status_code": 0},
        {"punch_timestamp": utc_iso(monday + timedelta(days=1), 17, 45), "raw_status_code": 1},
        # Wed: no punches (absence)
        # Thu: check-in only (missing checkout)
        {"punch_timestamp": utc_iso(monday + timedelta(days=3), 9, 0), "raw_status_code": 0},
        # Fri: on-time in, early out
        {"punch_timestamp": utc_iso(monday + timedelta(days=4), 9, 0), "raw_status_code": 0},
        {"punch_timestamp": utc_iso(monday + timedelta(days=4), 16, 30), "raw_status_code": 1},
    ]
    for p in punches:
        p["device_id"] = device["id"]
        p["device_user_id"] = "QAPAY"

    ingest = httpx.post(
        f"{API_BASE_URL}/internal/ingest/punches",
        json={"punches": punches},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
        timeout=15,
    )
    assert ingest.status_code == 200, ingest.text
    assert ingest.json()["inserted"] == len(punches)

    recompute = c.post(
        "/attendance/recompute",
        json={"date_from": str(monday), "date_to": str(monday + timedelta(days=4)), "employee_id": payroll_emp["id"]},
    )
    assert recompute.status_code in (200, 204), recompute.text

    return {
        "loc_a": loc_a,
        "loc_b": loc_b,
        "sched_a": sched_a,
        "emp_a": emp_a,
        "emp_b": emp_b,
        "payroll_emp": payroll_emp,
        "device": device,
        "mgr_a": mgr_a,
        "mgr_b": mgr_b,
        "penalty_cfg": penalty_cfg,
        "overtime_cfg": overtime_cfg,
        "monday": monday,
    }
