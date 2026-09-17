"""End-to-end smoke suite — chronos backend, against the live Docker Compose
stack (real Postgres, real FastAPI process, no mocks).

Covers the core flows from BLUEPRINT.md and re-verifies the specific
SECURITY_REPORT.md patches this project's QA pass was asked to confirm
end-to-end: bulk-import clean error messages + 10MB cap, location-based
manager scoping, missing-checkout not generating a bogus penalty, and the
two-layer (shift-grace + penalty-config-allowance) lateness grace period.

All test data is namespaced with a per-session random suffix (see
conftest.py) and torn down after the run. Requires `docker compose up` to
already be running (see conftest.py module docstring for how to run this
file).
"""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from conftest import (
    API_BASE_URL,
    INTERNAL_API_KEY,
    RUN_SUFFIX,
    _compose_exec_python,
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_login_rejects_bad_password():
    # Per-run username: auth.py's throttle is keyed on the username and its
    # counter lives 15 minutes in the api process, so a fixed name here
    # silently turns into a 429 on the 6th suite run inside that window.
    r = httpx.post(
        f"{API_BASE_URL}/auth/login",
        json={"username": f"qa_nonexistent_{RUN_SUFFIX}", "password": "wrong"},
    )
    assert r.status_code == 401


def test_session_cookie_is_httponly_and_survives_a_round_trip(admin_client, qa_username, qa_password):
    """Direct exercise of the PyJWT 2.9.0 -> 2.13.0 bump
    (SECURITY_REPORT.md Revision 3 finding 38): issue a real token, use it,
    and confirm the cookie's own hardening is unchanged.

    Depends on `admin_client` so the account exists first — auth.py
    rate-limits *per account*, so failed logins here would lock out the
    fixture's own login.
    """
    client = httpx.Client(base_url=API_BASE_URL, timeout=15)
    r = client.post("/auth/login", json={"username": qa_username, "password": qa_password})
    assert r.status_code == 204, r.text

    cookie = r.headers.get("set-cookie", "")
    assert "httponly" in cookie.lower()
    assert "samesite" in cookie.lower()

    assert client.get("/auth/me").status_code == 200
    client.close()


@pytest.mark.parametrize("label,mangle", [
    ("broken signature", lambda t: t[:-4] + ("aaaa" if not t.endswith("aaaa") else "bbbb")),
    ("empty signature", lambda t: ".".join(t.split(".")[:2]) + "."),
    ("alg=none downgrade", lambda t: "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0." + t.split(".")[1] + "."),
    ("not a jwt", lambda t: "not-a-jwt-at-all"),
])
def test_tampered_session_token_is_rejected(admin_client, label, mangle):
    """Signature verification still holds on the bumped PyJWT — including
    the classic `alg: none` downgrade. Reuses the fixture's already-issued
    cookie rather than logging in again (per-account rate limit)."""
    name, token = next(iter(admin_client.cookies.items()))

    tampered = httpx.Client(base_url=API_BASE_URL, timeout=15)
    tampered.cookies.set(name, mangle(token))
    r = tampered.get("/auth/me")
    assert r.status_code == 401, f"{label}: {r.status_code} {r.text}"
    tampered.close()


def test_repeated_failed_logins_are_rate_limited(admin_client):
    """Per-account throttle in auth.py (5 attempts / 15 min). Uses a
    dedicated throwaway account so it cannot lock out anything else, and a
    successful login clears the counter again."""
    username = f"qa_ratelimit_{RUN_SUFFIX}"
    password = "RateLimit123!"
    admin_client.post("/users", json={"username": username, "password": password, "role": "manager"})

    client = httpx.Client(base_url=API_BASE_URL, timeout=15)
    codes = [client.post("/auth/login", json={"username": username, "password": "wrong"}).status_code for _ in range(6)]
    assert codes[0] == 401
    assert 429 in codes, codes

    _compose_exec_python(
        f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM users WHERE username = :u"), {{"u": {username!r}}})
db.commit()
db.close()
"""
    )
    client.close()


def test_security_dependency_pins_are_installed_in_the_running_api():
    """Finding 38 bumped PyJWT and python-multipart for advisories reachable
    from the session-cookie and CSV-upload paths. Assert the *running*
    container actually has them, not just requirements.txt."""
    versions = _compose_exec_python(
        "from importlib.metadata import version;"
        "print(version('PyJWT'), version('python-multipart'))"
    ).split()
    pyjwt, multipart = versions[0], versions[1]

    def tup(v):
        return tuple(int(part) for part in v.split(".")[:3])

    assert tup(pyjwt) >= (2, 13, 0), f"PyJWT {pyjwt} predates the security bump"
    assert tup(multipart) >= (0, 0, 31), f"python-multipart {multipart} predates the security bump"


def test_admin_login_and_me(admin_client: httpx.Client):
    r = admin_client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"
    assert r.json()["must_change_password"] is False


def test_manager_must_change_password_gate_blocks_api(admin_client):
    """New HR-created manager accounts must be forced to change their
    password before touching any other endpoint (SECURITY_REPORT.md
    finding 1) — server-side gate, not just a frontend redirect."""
    username = f"qa_mgr_gatecheck_{RUN_SUFFIX}"
    admin_client.post("/users", json={"username": username, "password": "GateCheck123!", "role": "manager"})

    client = httpx.Client(base_url=API_BASE_URL, timeout=15)
    r = client.post("/auth/login", json={"username": username, "password": "GateCheck123!"})
    assert r.status_code == 204

    r = client.get("/employees")
    assert r.status_code == 403
    assert "password" in r.json()["detail"].lower()

    r = client.patch("/auth/me/password", json={"current_password": "GateCheck123!", "new_password": "GateCheckNew123!"})
    assert r.status_code == 204

    r = client.get("/employees")
    assert r.status_code == 200  # gate cleared after self-service change
    client.close()

    _compose_exec_python(
        f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM users WHERE username = :u"), {{"u": {username!r}}})
db.commit()
db.close()
"""
    )


# ---------------------------------------------------------------------------
# Pagination — regression test for the `total` miscount bug found during
# this QA pass (backend/app/pagination.py: `with_entities(func.count())`
# dropped the FROM clause on unjoined queries, always returning 1).
# ---------------------------------------------------------------------------

def test_pagination_total_matches_actual_row_count(admin_client, world):
    r = admin_client.get("/employees", params={"location_id": world["loc_a"]["id"], "page_size": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["items"])
    assert body["total"] >= 2  # emp_a + payroll_emp at minimum


# ---------------------------------------------------------------------------
# Location-based manager scoping (BLUEPRINT.md Section 6.2/6.3)
# ---------------------------------------------------------------------------

def test_manager_sees_only_own_location_employees(world):
    r = world["mgr_a"].get("/employees", params={"page_size": 100})
    assert r.status_code == 200
    codes = {e["employee_code"] for e in r.json()["items"]}
    assert world["emp_a"]["employee_code"] in codes
    assert world["payroll_emp"]["employee_code"] in codes
    assert world["emp_b"]["employee_code"] not in codes


def test_manager_cannot_view_other_location_employee_detail(world):
    r = world["mgr_a"].get(f"/employees/{world['emp_b']['id']}")
    assert r.status_code == 403

    r = world["mgr_a"].get(f"/employees/{world['emp_a']['id']}")
    assert r.status_code == 200


def test_manager_with_no_location_sees_empty_not_error(admin_client, world):
    """Transition behavior per BLUEPRINT.md 6.2: a manager with
    location_id = NULL must fail closed (empty results), never 403/500 and
    never all-rows."""
    sfx = RUN_SUFFIX
    username = f"qa_mgr_nolocation_{sfx}"
    admin_client.post("/users", json={"username": username, "password": "NoLoc123!", "role": "manager"})
    mc = httpx.Client(base_url=API_BASE_URL, timeout=15)
    mc.post("/auth/login", json={"username": username, "password": "NoLoc123!"})
    mc.patch("/auth/me/password", json={"current_password": "NoLoc123!", "new_password": "NoLoc123New!"})

    r = mc.get("/employees", params={"page_size": 100})
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["total"] == 0
    mc.close()

    # cleanup (not namespaced into `world`'s teardown query set since it has
    # no employee_code/location tie-in)
    _compose_exec_python(
        f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM users WHERE username = :u"), {{"u": {username!r}}})
db.commit()
db.close()
"""
    )


# ---------------------------------------------------------------------------
# Payroll calculation correctness — including the two-layer grace period and
# the missing-checkout fix (recompute.py) holding through to payroll.
# ---------------------------------------------------------------------------

def test_daily_status_missing_checkout_has_no_early_departure_or_overtime(admin_client, world):
    thu = world["monday"] + timedelta(days=3)
    r = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": world["payroll_emp"]["id"], "date_from": str(thu), "date_to": str(thu)},
    )
    row = r.json()["items"][0]
    assert row["actual_first_in"] is not None
    assert row["actual_last_out"] == row["actual_first_in"]  # recompute.py: no real checkout punch
    assert row["early_departure_minutes"] == 0
    assert row["overtime_minutes"] == 0
    assert row["status"] == "present"  # not "late" either


def test_reports_alerts_flags_missing_checkout(admin_client, world):
    r = admin_client.get("/reports/alerts", params={"days": 30, "location_id": world["loc_a"]["id"]})
    assert r.status_code == 200
    alerts = r.json()["alerts"]
    matches = [a for a in alerts if a["type"] == "missing_checkout" and a["employee_id"] == world["payroll_emp"]["id"]]
    assert len(matches) == 1
    assert matches[0]["work_date"] == str(world["monday"] + timedelta(days=3))


def test_manager_alerts_excludes_admin_only_types(world):
    r = world["mgr_a"].get("/reports/alerts", params={"days": 30})
    assert r.status_code == 200
    types = {a["type"] for a in r.json()["alerts"]}
    assert "missing_checkout" in types  # location-scoped type, manager can see it
    assert "device_stale" not in types
    assert "unresolved_punches" not in types
    assert "manager_no_location" not in types


def test_payroll_run_calculation_matches_expected_formula(admin_client, world):
    payroll_emp = world["payroll_emp"]
    monday = world["monday"]

    r = admin_client.post(
        "/payroll/runs",
        json={"period_year": monday.year, "period_month": monday.month, "location_id": world["loc_a"]["id"]},
    )
    assert r.status_code == 201, r.text
    run = r.json()

    line = admin_client.get(f"/payroll/runs/{run['id']}/lines/{payroll_emp['id']}").json()

    # Mon: late_minutes = (09:20 - (09:00+5min grace)) = 15min.
    # threshold_allowance: 15 > allowance(10) -> flat_amount 15.00.
    # Fri: early_departure_minutes = 30 (16:30 vs 17:00).
    #   early penalty = 30 * 0.20 = 6.00.
    # Total lateness/early penalty = 15.00 + 6.00 = 21.00 (under the 50 cap).
    assert line["total_late_minutes"] == 15
    assert line["total_lateness_penalty_eur"] == pytest.approx(21.00)

    # Tue: raw overtime = 45min (17:45 vs 17:00), daily threshold 30min
    # subtracted at recompute time -> 15min stored. Payroll: daily basis, no
    # further threshold subtraction. bonus = 15/60 * 10.00/hr = 2.50.
    assert line["total_overtime_minutes"] == 15
    assert line["total_overtime_bonus_eur"] == pytest.approx(2.50)

    # Wed: absent. absence_rule_config seed: full_day_salary_fraction,
    # deduction_value=1.0 -> base_salary/days_in_month * 1.0.
    import calendar
    days_in_month = calendar.monthrange(monday.year, monday.month)[1]
    expected_absence = round(float(payroll_emp["base_salary_eur"]) / days_in_month, 2)
    assert line["total_absence_days"] == 1.0
    assert line["total_absence_deduction_eur"] == pytest.approx(expected_absence, abs=0.01)

    expected_net = round(
        float(payroll_emp["base_salary_eur"]) - 21.00 - line["total_absence_deduction_eur"] + 2.50, 2
    )
    assert line["net_pay_eur"] == pytest.approx(expected_net, abs=0.01)

    # Adjustments round-trip into net pay.
    admin_client.post(
        f"/payroll/runs/{run['id']}/lines/{payroll_emp['id']}/adjustments",
        json={"type": "bonus", "amount_eur": 50.00, "reason": "QA smoke test bonus"},
    )
    line2 = admin_client.get(f"/payroll/runs/{run['id']}/lines/{payroll_emp['id']}").json()
    assert line2["net_pay_eur"] == pytest.approx(expected_net + 50.00, abs=0.01)

    # Leave the run in draft (not finalized) so teardown can delete it.
    del_resp = admin_client.delete(f"/payroll/runs/{run['id']}")
    assert del_resp.status_code == 204


# ---------------------------------------------------------------------------
# Leave approval scoping + feed-back into daily status
# ---------------------------------------------------------------------------

def test_leave_approval_scoped_and_feeds_recompute(admin_client, world):
    # leave_types.name became name_en/name_sq in migration
    # 0007_leave_type_bilingual_name — both are required by LeaveTypeCreate.
    r = admin_client.post(
        "/leave-types",
        json={
            "name_en": f"QA Leave Type {RUN_SUFFIX}",
            "name_sq": f"QA Lloji Lejes {RUN_SUFFIX}",
            "is_paid": True,
            "requires_approval": True,
            "is_active": True,
        },
    )
    assert r.status_code == 201, r.text
    leave_type = r.json()

    start = world["monday"] + timedelta(days=30)
    end = start + timedelta(days=1)
    leave = admin_client.post(
        "/leave-records",
        json={
            "employee_id": world["emp_a"]["id"],
            "leave_type_id": leave_type["id"],
            "start_date": str(start),
            "end_date": str(end),
        },
    ).json()

    # Cross-location manager cannot approve.
    r = world["mgr_b"].patch(f"/leave-records/{leave['id']}/approve", json={})
    assert r.status_code == 403

    # Same-location manager can.
    r = world["mgr_a"].patch(f"/leave-records/{leave['id']}/approve", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    # Recompute already triggered by the approval itself (leave.py calls
    # recompute_range inline) — confirm the daily-status row reflects it.
    r = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": world["emp_a"]["id"], "date_from": str(start), "date_to": str(start)},
    )
    assert r.json()["items"][0]["status"] == "on_leave"
    # leave_type has no DELETE endpoint by design; teardown SQL (conftest.py)
    # removes it via the `QA Leave Type {suffix}` name pattern.


def test_leave_type_defaults_to_no_approval_workflow(admin_client, world):
    """Client direction 2026-08-27 (see schemas.py LeaveTypeCreate): a leave
    type created without an explicit `requires_approval` records leave that
    counts immediately, with no approval step."""
    lt = admin_client.post(
        "/leave-types",
        json={"name_en": f"QA NoApproval LT {RUN_SUFFIX}", "name_sq": f"QA PaAprovim LT {RUN_SUFFIX}", "is_paid": True},
    )
    assert lt.status_code == 201, lt.text
    lt = lt.json()
    assert lt["requires_approval"] is False

    day = world["monday"] + timedelta(days=45)
    rec = admin_client.post(
        "/leave-records",
        json={"employee_id": world["emp_b"]["id"], "leave_type_id": lt["id"], "start_date": str(day), "end_date": str(day)},
    )
    assert rec.status_code == 201, rec.text
    rec = rec.json()
    assert rec["status"] == "approved"
    assert rec["approved_at"] is not None

    # Approved on creation means recompute already ran.
    row = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": world["emp_b"]["id"], "date_from": str(day), "date_to": str(day)},
    ).json()["items"][0]
    assert row["status"] == "on_leave"

    # And there is nothing left to action.
    r = admin_client.patch(f"/leave-records/{rec['id']}/approve", json={})
    assert r.status_code == 400

    assert admin_client.delete(f"/leave-records/{rec['id']}").status_code == 204


# ---------------------------------------------------------------------------
# Payroll run lifecycle: create -> adjust -> finalize -> Excel export
# (BLUEPRINT.md Section 4.8). Kept separate from the calculation test above
# so that one can keep deleting its draft run.
# ---------------------------------------------------------------------------

def test_payroll_run_finalize_and_excel_exports(admin_client, world):
    import io
    import zipfile

    payroll_emp = world["payroll_emp"]
    # A period of its own, so this never collides with the calculation test's
    # run on the one-run-per-location-and-period constraint.
    prev_month_anchor = world["monday"].replace(day=1) - timedelta(days=1)

    r = admin_client.post(
        "/payroll/runs",
        json={"period_year": prev_month_anchor.year, "period_month": prev_month_anchor.month, "location_id": world["loc_a"]["id"]},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    assert run["status"] == "draft"

    # The draft run's Excel export works before finalization...
    r = admin_client.get(f"/payroll/runs/{run['id']}/export.xlsx")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert "attachment" in r.headers["content-disposition"]
    assert zipfile.is_zipfile(io.BytesIO(r.content)), "export is not a real .xlsx (OOXML zip) payload"

    # ...but a payslip is only issued for a finalized run.
    r = admin_client.get(f"/payroll/runs/{run['id']}/lines/{payroll_emp['id']}/payslip.xlsx")
    assert r.status_code == 400

    r = admin_client.post(f"/payroll/runs/{run['id']}/finalize")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "finalized"
    assert r.json()["finalized_at"] is not None

    r = admin_client.get(f"/payroll/runs/{run['id']}/lines/{payroll_emp['id']}/payslip.xlsx")
    assert r.status_code == 200, r.text
    assert zipfile.is_zipfile(io.BytesIO(r.content))

    # A finalized run is immutable: no new adjustments, no deletion,
    # no second finalize.
    r = admin_client.post(
        f"/payroll/runs/{run['id']}/lines/{payroll_emp['id']}/adjustments",
        json={"type": "bonus", "amount_eur": 10.00, "reason": "QA post-finalize attempt"},
    )
    assert r.status_code == 400
    assert admin_client.post(f"/payroll/runs/{run['id']}/finalize").status_code == 400
    assert admin_client.delete(f"/payroll/runs/{run['id']}").status_code == 400
    # conftest.py's teardown removes it directly (test cleanup is not a
    # business operation — see its comment).


def test_manager_cannot_reach_another_locations_payroll_run(admin_client, world):
    r = admin_client.post(
        "/payroll/runs",
        json={"period_year": 2018, "period_month": 3, "location_id": world["loc_a"]["id"]},
    )
    assert r.status_code == 201, r.text
    run = r.json()
    try:
        assert world["mgr_a"].get(f"/payroll/runs/{run['id']}").status_code == 200
        assert world["mgr_b"].get(f"/payroll/runs/{run['id']}").status_code == 403
        assert world["mgr_b"].get(f"/payroll/runs/{run['id']}/export.xlsx").status_code == 403
        assert world["mgr_b"].post(f"/payroll/runs/{run['id']}/finalize").status_code == 403
    finally:
        admin_client.delete(f"/payroll/runs/{run['id']}")


# ---------------------------------------------------------------------------
# CSV bulk-import — SECURITY_REPORT.md findings 20-22
# ---------------------------------------------------------------------------

def test_bulk_import_employees_clean_errors_and_success(admin_client, world):
    sfx = RUN_SUFFIX
    csv_text = (
        "location_id,employee_code,first_name,last_name,job_title,hire_date,base_salary_eur,manager_user_id,employment_status\n"
        f"{world['loc_a']['id']},QA-BULKOK-{sfx},First,Last,Tester,2025-02-01,900.00,,active\n"
        f"{world['loc_a']['id']},QA-BULKBADMGR-{sfx},First,Last,Tester,2025-02-01,900.00,999999,active\n"
        f"{world['loc_a']['id']},{world['emp_a']['employee_code']},Dup,Code,Tester,2025-02-01,900.00,,active\n"
    )
    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": ("employees.csv", csv_text, "text/csv")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1
    errors_by_row = {e["row"]: e["message"] for e in body["errors"]}
    assert errors_by_row[3] == "Manager not found"  # clean message, not a raw FK constraint string
    assert "constraint" not in errors_by_row[3].lower()
    assert "fkey" not in errors_by_row[3].lower()
    assert errors_by_row[4] == "Employee code must be unique"


def test_bulk_import_rejects_oversized_file_with_413(admin_client):
    header = "location_id,employee_code,first_name,last_name,job_title,hire_date,base_salary_eur,manager_user_id,employment_status\n"
    row = "1,QA-BIGROW,First,Last,Tester,2025-01-01,900.00,,active\n"
    # Just over 10MB.
    target_bytes = 10 * 1024 * 1024 + 1024
    n_rows = target_bytes // len(row) + 1
    csv_text = header + row * n_rows

    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": ("big.csv", csv_text, "text/csv")},
        timeout=60,
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_bulk_import_accepts_a_real_xlsx_upload(admin_client, world):
    """python-multipart 0.0.20 -> 0.0.31 (finding 38) sits on exactly this
    path, and the .xlsx branch is the binary one — a part-header or
    separator parsing differential would surface here first.

    Builds a genuine OOXML workbook by hand (minimal but real) rather than
    adding an openpyxl test dependency.
    """
    import io
    import zipfile

    sfx = RUN_SUFFIX
    rows = [
        ["location_id", "employee_code", "first_name", "last_name", "hire_date", "base_salary_eur", "employment_status"],
        [str(world["loc_a"]["id"]), f"QA-XLSX-{sfx}", "Excel", "Import", "2025-03-01", "950.00", "active"],
    ]

    def cell(ref, value):
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'

    sheet_rows = "".join(
        "<row r=\"%d\">%s</row>" % (
            r_i + 1,
            "".join(cell(f"{chr(ord('A') + c_i)}{r_i + 1}", v) for c_i, v in enumerate(row)),
        )
        for r_i, row in enumerate(rows)
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                   '</Relationships>')
        z.writestr("xl/worksheets/sheet1.xml",
                   '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   f'<sheetData>{sheet_rows}</sheetData></worksheet>')

    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": (
            "employees.xlsx",
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1, r.text

    listed = admin_client.get("/employees", params={"search": f"QA-XLSX-{sfx}", "page_size": 10}).json()
    assert any(e["employee_code"] == f"QA-XLSX-{sfx}" for e in listed["items"])


def test_bulk_import_rejects_a_corrupt_workbook_cleanly(admin_client):
    """A file that claims to be .xlsx but isn't must come back as a clean
    400, not a 500 — the upload path is a system boundary."""
    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": ("broken.xlsx", b"PK\x03\x04 not really a workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 400, r.text
    assert "could not read excel file" in r.json()["detail"].lower()


def test_bulk_import_of_non_tabular_text_creates_nothing(admin_client):
    """Falls through to the CSV parser, which finds a header and no data
    rows. The contract is "nothing created, no error, no crash"."""
    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": ("payload.txt", "this is not a spreadsheet", "text/plain")},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 0, "errors": []}


def test_bulk_import_of_undecodable_bytes_is_not_a_500(admin_client):
    """Invalid UTF-8 reaches `raw_bytes.decode()` in
    services/bulk_import.py. Whatever the chosen behaviour, it must be a
    4xx the caller can act on rather than an unhandled server error — an
    upload endpoint is a system boundary."""
    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": ("payload.csv", b"\xff\xfe\x00\x00binary garbage", "text/csv")},
    )
    assert r.status_code < 500, f"unhandled server error on malformed upload: {r.status_code} {r.text}"
    assert r.status_code == 400
    assert "UTF-8" in r.json()["detail"]


def test_bulk_import_of_csv_with_oversized_field_is_not_a_500(admin_client):
    """Decodes as UTF-8 but the csv module refuses to parse it: a field
    longer than csv.field_size_limit() (131072), which the 10 MB upload cap
    lets through. Second failure mode of the CSV branch, same boundary
    rule — it used to raise _csv.Error and return 500."""
    body = b"location_id,employee_code\n1," + b"x" * 200000 + b"\n"
    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": ("payload.csv", body, "text/csv")},
    )
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert r.json()["detail"].startswith("Could not read CSV file:")


def test_bulk_import_of_valid_utf8_csv_still_works(admin_client, world):
    """Guard against the new try/except swallowing the happy path."""
    csv_text = (
        "location_id,employee_code,first_name,last_name,hire_date,base_salary_eur\n"
        f"{world['loc_a']['id']},__dbgcsv-{RUN_SUFFIX},Ardit,Krasniqi,2026-01-05,1000.00\n"
    )
    r = admin_client.post(
        "/employees/bulk-import",
        files={"file": ("employees.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1, r.json()


def test_bulk_import_unauthenticated_rejected():
    csv_text = "location_id,employee_code,first_name,last_name,hire_date,base_salary_eur\n"
    r = httpx.post(
        f"{API_BASE_URL}/employees/bulk-import",
        files={"file": ("employees.csv", csv_text, "text/csv")},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Config CRUD — create, edit, deactivate (DESIGN_SPEC.md 5.21)
# ---------------------------------------------------------------------------

def test_config_penalty_edit_and_deactivate(admin_client, world):
    cfg = world["penalty_cfg"]

    r = admin_client.put(f"/config/penalty/{cfg['id']}", json={**{k: v for k, v in cfg.items() if k not in ("id", "location_name")}, "flat_amount_eur": 20.00})
    assert r.status_code == 200
    assert r.json()["flat_amount_eur"] == 20.00

    r = admin_client.put(f"/config/penalty/{cfg['id']}", json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # restore for any later assertions relying on world["penalty_cfg"] being active
    admin_client.put(f"/config/penalty/{cfg['id']}", json={"is_active": True})


# ---------------------------------------------------------------------------
# Manager operational access (2026-08-24 change): managers get CRUD on
# employees/shift-schedules/devices (+ nested enrollments/assignments)
# scoped to their own location, deps.py's require_manager_or_admin +
# assert_location_access.
# ---------------------------------------------------------------------------

def test_manager_operational_crud_scoped_to_location(world):
    mgr_a = world["mgr_a"]
    sfx = RUN_SUFFIX

    # Manager can create an employee at their own location.
    r = mgr_a.post(
        "/employees",
        json={
            "location_id": world["loc_a"]["id"],
            "employee_code": f"QA-MGRCREATE-{sfx}",
            "first_name": "Mgr",
            "last_name": "Created",
            "hire_date": "2025-01-01",
            "base_salary_eur": 800.00,
            "employment_status": "active",
        },
    )
    assert r.status_code == 201, r.text
    mgr_emp = r.json()

    # ...but not at another location.
    r = mgr_a.post(
        "/employees",
        json={
            "location_id": world["loc_b"]["id"],
            "employee_code": f"QA-MGRCROSS-{sfx}",
            "first_name": "Mgr",
            "last_name": "Cross",
            "hire_date": "2025-01-01",
            "base_salary_eur": 800.00,
            "employment_status": "active",
        },
    )
    assert r.status_code == 403

    # Manager can create a device at their own location.
    r = mgr_a.post(
        "/devices",
        json={"location_id": world["loc_a"]["id"], "label": f"QA Mgr Device {sfx}", "ip_address": "10.0.0.210", "port": 4370, "is_active": True},
    )
    assert r.status_code == 201, r.text
    mgr_device = r.json()

    # ...but not at another location.
    r = mgr_a.post(
        "/devices",
        json={"location_id": world["loc_b"]["id"], "label": f"QA Mgr Device Cross {sfx}", "ip_address": "10.0.0.211", "port": 4370, "is_active": True},
    )
    assert r.status_code == 403

    # Manager can create a shift schedule at their own location.
    r = mgr_a.post(
        "/shift-schedules",
        json={"location_id": world["loc_a"]["id"], "name": f"QA Mgr Sched {sfx}", "grace_minutes_late": 5, "is_active": True},
    )
    assert r.status_code == 201, r.text

    # ...but not at another location.
    r = mgr_a.post(
        "/shift-schedules",
        json={"location_id": world["loc_b"]["id"], "name": f"QA Mgr Sched Cross {sfx}", "grace_minutes_late": 5, "is_active": True},
    )
    assert r.status_code == 403

    # Manager can enroll a device for their own (same-location) employee.
    r = mgr_a.post(
        f"/employees/{mgr_emp['id']}/device-enrollments",
        json={"device_id": mgr_device["id"], "device_user_id": f"QAMGRENR{sfx}"},
    )
    assert r.status_code == 201, r.text

    # Manager can create a shift-assignment for their own employee.
    r = mgr_a.post(
        f"/employees/{mgr_emp['id']}/shift-assignments",
        json={"shift_schedule_id": world["sched_a"]["id"], "effective_from": "2025-06-01"},
    )
    assert r.status_code == 201, r.text

    # Manager cannot touch the other location's employee at all (enrollments/assignments nested under it).
    r = mgr_a.get(f"/employees/{world['emp_b']['id']}/device-enrollments")
    assert r.status_code == 403
    r = mgr_a.post(
        f"/employees/{world['emp_b']['id']}/shift-assignments",
        json={"shift_schedule_id": world["sched_a"]["id"], "effective_from": "2025-06-01"},
    )
    assert r.status_code == 403


def test_admin_unrestricted_across_locations(admin_client, world):
    for loc in (world["loc_a"], world["loc_b"]):
        r = admin_client.get("/employees", params={"location_id": loc["id"], "page_size": 5})
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# Payroll/config access by role (2026-08-25 change): the per-manager opt-in
# flag `users.can_manage_payroll` was dropped in migration
# 0008_drop_can_manage_payroll. A manager now reaches payroll and config
# purely by role (deps.py require_manager_or_admin), still row-scoped to
# their own location by assert_location_access.
# ---------------------------------------------------------------------------

def test_manager_payroll_and_config_access_by_role_scoped_to_location(admin_client, world):
    mgr_a = world["mgr_a"]
    me = mgr_a.get("/auth/me").json()
    # The flag is gone from the schema entirely — not just defaulted to false.
    assert "can_manage_payroll" not in me

    # Payroll + config are reachable with no opt-in of any kind...
    r = mgr_a.get("/payroll/runs")
    assert r.status_code == 200
    for run in r.json():
        assert run["location_id"] == world["loc_a"]["id"]

    r = mgr_a.get("/config/penalty")
    assert r.status_code == 200
    loc_ids = {c["location_id"] for c in r.json()}
    assert world["loc_a"]["id"] in loc_ids
    assert world["loc_b"]["id"] not in loc_ids

    # ...and a manager may run payroll for their own location. A period no
    # other test uses, so this never collides with the one-run-per-
    # location-and-period constraint.
    period = {"period_year": 2019, "period_month": 1}
    r = mgr_a.post("/payroll/runs", json={**period, "location_id": world["loc_a"]["id"]})
    assert r.status_code == 201, r.text
    mgr_run = r.json()
    assert mgr_run["location_id"] == world["loc_a"]["id"]
    assert mgr_a.delete(f"/payroll/runs/{mgr_run['id']}").status_code == 204

    # ...but never for another location.
    r = mgr_a.post("/payroll/runs", json={**period, "location_id": world["loc_b"]["id"]})
    assert r.status_code == 403


def test_manager_with_no_location_sees_no_payroll_runs(admin_client):
    """SECURITY_REPORT.md Revision 3 finding 39: `location_id == None`
    compiled to `IS NULL`, which is the *org-wide* payroll scope — so a
    manager with no assigned location saw every company-wide run instead of
    nothing. Must fail closed like every other scoped list.

    payroll_runs.location_id is nullable in the DB but PayrollRunCreate pins
    it to an int, so the org-wide run this regression needs can only be
    planted directly (same bootstrap mechanism conftest.py uses)."""
    username = f"qa_mgr_nopayroll_{RUN_SUFFIX}"
    admin_client.post("/users", json={"username": username, "password": "NoPay123!", "role": "manager"})
    admin_id = admin_client.get("/auth/me").json()["id"]

    run_id = int(
        _compose_exec_python(
            f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
rid = db.execute(text(
    "INSERT INTO payroll_runs (location_id, period_year, period_month, status, generated_by_user_id) "
    "VALUES (NULL, 2019, 1, 'draft', :u) RETURNING id"
), {{"u": {admin_id!r}}}).scalar()
db.commit()
print(rid)
db.close()
"""
        )
    )

    try:
        # Admin sees the org-wide run...
        assert run_id in {r["id"] for r in admin_client.get("/payroll/runs").json()}

        mc = httpx.Client(base_url=API_BASE_URL, timeout=15)
        mc.post("/auth/login", json={"username": username, "password": "NoPay123!"})
        mc.patch("/auth/me/password", json={"current_password": "NoPay123!", "new_password": "NoPay123New!"})

        # ...the location-less manager sees nothing at all.
        r = mc.get("/payroll/runs")
        assert r.status_code == 200
        assert r.json() == []
        mc.close()
    finally:
        _compose_exec_python(
            f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM payroll_runs WHERE id = :r"), {{"r": {run_id!r}}})
db.execute(text("DELETE FROM users WHERE username = :u"), {{"u": {username!r}}})
db.commit()
db.close()
"""
        )


def test_admin_payroll_and_config_access_unrestricted(admin_client):
    r = admin_client.get("/payroll/runs")
    assert r.status_code == 200
    r = admin_client.get("/config/penalty")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Live daily-status recompute on punch ingest (internal.py's ingest_punches
# now calls recompute_employee_date immediately) + the dashboard KPIs that
# depend on it being live: present-includes-late, "On Site Now" sub-metric.
# ---------------------------------------------------------------------------

def test_live_recompute_and_onsite_kpi_update_immediately_on_ingest(admin_client, world):
    sfx = RUN_SUFFIX
    tz = ZoneInfo("Europe/Tirane")
    today_local = datetime.now(tz).date()

    emp = admin_client.post(
        "/employees",
        json={
            "location_id": world["loc_a"]["id"],
            "employee_code": f"QA-TODAY-{sfx}",
            "first_name": "QA",
            "last_name": "Today",
            "hire_date": "2025-01-01",
            "base_salary_eur": 900.00,
            "employment_status": "active",
        },
    ).json()
    admin_client.post(
        f"/employees/{emp['id']}/shift-assignments",
        json={"shift_schedule_id": world["sched_a"]["id"], "effective_from": "2025-01-01"},
    )
    device_user_id = f"QATODAY{sfx}"
    admin_client.post(
        f"/employees/{emp['id']}/device-enrollments",
        json={"device_id": world["device"]["id"], "device_user_id": device_user_id},
    )

    def summary():
        r = admin_client.get("/reports/dashboard-summary", params={"location_id": world["loc_a"]["id"]})
        assert r.status_code == 200
        return r.json()

    def ingest_now(offset_minutes: int, raw_status_code: int):
        ts = (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).isoformat()
        r = httpx.post(
            f"{API_BASE_URL}/internal/ingest/punches",
            json={"punches": [{
                "punch_timestamp": ts,
                "raw_status_code": raw_status_code,
                "device_id": world["device"]["id"],
                "device_user_id": device_user_id,
            }]},
            headers={"X-Internal-Key": INTERNAL_API_KEY},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        return r.json()

    # No punches yet today -> no daily-status row at all (never mind stale/blank).
    r = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": emp["id"], "date_from": str(today_local), "date_to": str(today_local)},
    )
    assert r.json()["items"] == []

    before = summary()

    # Check-in "now" -- with the shared schedule (09:00 + 5min grace) and the
    # real current time being well past shift start, this lands as `late`.
    ingest_now(0, 0)  # check_in_work

    row = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": emp["id"], "date_from": str(today_local), "date_to": str(today_local)},
    ).json()["items"][0]
    # Live recompute, not the nightly-only path: the row exists immediately,
    # with no need to wait for anything.
    assert row["status"] in ("present", "late")
    assert row["actual_first_in"] is not None

    after_checkin = summary()
    # present_today includes late (item 3): the delta must be +1 whichever
    # of the two statuses this landed as.
    assert after_checkin["present_today"] == before["present_today"] + 1
    assert after_checkin["present_today"] >= after_checkin["late_today"]
    if row["status"] == "late":
        assert after_checkin["late_today"] == before["late_today"] + 1
    # On Site Now: went up immediately, live, right after ingest -- no manual
    # recompute call was made anywhere in this test.
    assert after_checkin["on_site_now"] == before["on_site_now"] + 1

    # Break-out (raw_status_code 2, explicit break classification) -- still
    # on site, must NOT be read as "left" (only a real check_out_work should
    # drop them from On Site Now).
    ingest_now(5, 2)  # check_out_break
    after_break = summary()
    assert after_break["on_site_now"] == before["on_site_now"] + 1

    # Real check-out -- now they've left, drops back to baseline immediately.
    ingest_now(10, 1)  # check_out_work
    after_checkout = summary()
    assert after_checkout["on_site_now"] == before["on_site_now"]


# ---------------------------------------------------------------------------
# Alerts sorted newest-first by date (reports.py alerts endpoint).
# ---------------------------------------------------------------------------

def test_alerts_sorted_newest_first_by_date(admin_client, world):
    sfx = RUN_SUFFIX
    tz = ZoneInfo("Europe/Tirane")
    monday = world["monday"]
    # Two distinct, already-elapsed *working* days (the shared schedule has
    # Sat/Sun as non-working, which produces no missing_checkout row), one
    # clearly before the other. Both inside the 60-day window queried below.
    earlier_date = monday - timedelta(days=7)   # previous Monday
    later_date = monday + timedelta(days=3)     # that week's Thursday

    emp = admin_client.post(
        "/employees",
        json={
            "location_id": world["loc_a"]["id"],
            "employee_code": f"QA-ALERTORDER-{sfx}",
            "first_name": "QA",
            "last_name": "AlertOrder",
            "hire_date": "2025-01-01",
            "base_salary_eur": 900.00,
            "employment_status": "active",
        },
    ).json()
    admin_client.post(
        f"/employees/{emp['id']}/shift-assignments",
        json={"shift_schedule_id": world["sched_a"]["id"], "effective_from": "2025-01-01"},
    )
    device_user_id = f"QAALERT{sfx}"
    admin_client.post(
        f"/employees/{emp['id']}/device-enrollments",
        json={"device_id": world["device"]["id"], "device_user_id": device_user_id},
    )

    def utc_iso(d, h, m):
        return datetime(d.year, d.month, d.day, h, m, tzinfo=tz).astimezone(ZoneInfo("UTC")).isoformat()

    punches = [
        {"punch_timestamp": utc_iso(earlier_date, 9, 0), "raw_status_code": 0, "device_id": world["device"]["id"], "device_user_id": device_user_id},
        {"punch_timestamp": utc_iso(later_date, 9, 0), "raw_status_code": 0, "device_id": world["device"]["id"], "device_user_id": device_user_id},
    ]
    r = httpx.post(
        f"{API_BASE_URL}/internal/ingest/punches",
        json={"punches": punches},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
        timeout=15,
    )
    assert r.status_code == 200, r.text

    r = admin_client.post(
        "/attendance/recompute",
        json={"date_from": str(earlier_date), "date_to": str(later_date), "employee_id": emp["id"]},
    )
    assert r.status_code in (200, 204)

    r = admin_client.get("/reports/alerts", params={"days": 60, "location_id": world["loc_a"]["id"]})
    assert r.status_code == 200
    alerts = r.json()["alerts"]

    missing = [a for a in alerts if a["type"] == "missing_checkout" and a["employee_id"] == emp["id"]]
    assert {a["work_date"] for a in missing} == {str(earlier_date), str(later_date)}

    dated = [a["work_date"] for a in alerts if a["work_date"] is not None]
    assert dated == sorted(dated, reverse=True)  # global newest-first invariant

    idx_later = next(
        i for i, a in enumerate(alerts)
        if a["type"] == "missing_checkout" and a["employee_id"] == emp["id"] and a["work_date"] == str(later_date)
    )
    idx_earlier = next(
        i for i, a in enumerate(alerts)
        if a["type"] == "missing_checkout" and a["employee_id"] == emp["id"] and a["work_date"] == str(earlier_date)
    )
    assert idx_later < idx_earlier


# ---------------------------------------------------------------------------
# Leave workflow changes: manager-initiated requests (scoped), requires_approval
# actually honored (auto-approve feeds recompute immediately), delete allowed
# for auto-approved records but still blocked for a manually-approved one.
# Also: on_leave_today KPI (name + leave-type "reason" + date range, scoped).
# ---------------------------------------------------------------------------

def test_manager_created_leave_and_requires_approval_and_on_leave_kpi(admin_client, world):
    sfx = RUN_SUFFIX
    tz = ZoneInfo("Europe/Tirane")
    today_local = datetime.now(tz).date()
    mgr_a = world["mgr_a"]
    mgr_b = world["mgr_b"]

    lt_approval = admin_client.post(
        "/leave-types",
        json={
            "name_en": f"QA Approval LT {sfx}",
            "name_sq": f"QA Aprovim LT {sfx}",
            "is_paid": True,
            "requires_approval": True,
            "is_active": True,
        },
    ).json()
    lt_auto = admin_client.post(
        "/leave-types",
        json={
            "name_en": f"QA Auto LT {sfx}",
            "name_sq": f"QA Auto LT SQ {sfx}",
            "is_paid": True,
            "requires_approval": False,
            "is_active": True,
        },
    ).json()

    # Manager can create a leave request for their own-location employee.
    r = mgr_a.post(
        "/leave-records",
        json={
            "employee_id": world["emp_a"]["id"],
            "leave_type_id": lt_approval["id"],
            "start_date": str(today_local),
            "end_date": str(today_local),
        },
    )
    assert r.status_code == 201, r.text
    pending_rec = r.json()
    # requires_approval=true -> lands as pending, not auto-approved.
    assert pending_rec["status"] == "pending"

    # Manager cannot create a leave request for another location's employee.
    r = mgr_a.post(
        "/leave-records",
        json={
            "employee_id": world["emp_b"]["id"],
            "leave_type_id": lt_approval["id"],
            "start_date": str(today_local),
            "end_date": str(today_local),
        },
    )
    assert r.status_code == 403

    # The still-pending request must not show up as "on leave" yet.
    r = admin_client.get("/reports/dashboard-summary", params={"location_id": world["loc_a"]["id"]})
    onleave_ids_before = {e["employee_id"] for e in r.json()["on_leave_employees"]}
    assert world["emp_a"]["id"] not in onleave_ids_before

    # requires_approval=false -> auto-approved immediately, feeds recompute right away.
    r = mgr_a.post(
        "/leave-records",
        json={
            "employee_id": world["emp_a"]["id"],
            "leave_type_id": lt_auto["id"],
            "start_date": str(today_local),
            "end_date": str(today_local),
        },
    )
    assert r.status_code == 201, r.text
    auto_rec = r.json()
    assert auto_rec["status"] == "approved"

    r = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": world["emp_a"]["id"], "date_from": str(today_local), "date_to": str(today_local)},
    )
    assert r.json()["items"][0]["status"] == "on_leave"

    # on_leave_today KPI: name, correct leave-type "reason", date range, scoped to loc A.
    r = admin_client.get("/reports/dashboard-summary", params={"location_id": world["loc_a"]["id"]})
    body = r.json()
    onleave = {e["employee_id"]: e for e in body["on_leave_employees"]}
    assert world["emp_a"]["id"] in onleave
    entry = onleave[world["emp_a"]["id"]]
    assert entry["employee_name"] == f"{world['emp_a']['first_name']} {world['emp_a']['last_name']}"
    # Bilingual since migration 0007 — the dashboard carries both so the UI
    # can render whichever language the user picked.
    assert entry["leave_type_name_en"] == lt_auto["name_en"]
    assert entry["leave_type_name_sq"] == lt_auto["name_sq"]
    assert entry["start_date"] == str(today_local)
    assert entry["end_date"] == str(today_local)
    assert body["on_leave_today"] >= 1

    # Scoped correctly for managers: mgr_a (same location) sees it, mgr_b (other) doesn't.
    r = mgr_a.get("/reports/dashboard-summary")
    assert world["emp_a"]["id"] in {e["employee_id"] for e in r.json()["on_leave_employees"]}
    r = mgr_b.get("/reports/dashboard-summary")
    assert world["emp_a"]["id"] not in {e["employee_id"] for e in r.json()["on_leave_employees"]}

    # Deleting the auto-approved (non-manually-approved) record is now allowed.
    r = admin_client.delete(f"/leave-records/{auto_rec['id']}")
    assert r.status_code == 204

    # A record an admin manually approves is still protected from deletion.
    r = admin_client.patch(f"/leave-records/{pending_rec['id']}/approve", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    r = admin_client.delete(f"/leave-records/{pending_rec['id']}")
    assert r.status_code == 400
