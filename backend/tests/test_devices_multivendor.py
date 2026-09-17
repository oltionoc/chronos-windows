"""Multi-vendor device coverage — BLUEPRINT.md Section 5.5 plus the
SECURITY_REPORT.md Revision 3 invariants that touch live behaviour.

Two things are being proved here at once, and they pull in opposite
directions, so most tests assert both halves:

  * the feature still works — all three `device_type` values round-trip
    through the real API, and a vendor-supplied `punch_type_hint` is trusted
    end to end instead of being re-derived by services/classify.py;
  * the Revision 3 patches hold — credential re-supply on retarget, the
    hikvision_cloud host allowlist, bare-host validation, generic
    test-connection errors, `punch_type_hint` refused for ZKTeco, and config
    location scoping.

Same conventions as test_qa_smoke.py: real Docker Compose stack over HTTP,
no mocks, everything namespaced with conftest.py's per-session RUN_SUFFIX and
removed by its teardown. Neither Hikvision transport can be exercised against
real hardware (none exists), so this file covers the schema/API round-trips
and the guard rails; the adapters' own parsing and paging logic is covered by
test_device_adapters.py.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from conftest import API_BASE_URL, RUN_SUFFIX, _compose_exec_python

INTERNAL_API_KEY = _compose_exec_python(
    "from app.config import settings; print(settings.internal_api_key)"
)

CLOUD_HOST = "open.hik-connect.com"
STORED_PASSWORD = "StoredDevicePw123"


def _ingest(punches):
    return httpx.post(
        f"{API_BASE_URL}/internal/ingest/punches",
        json={"punches": punches},
        headers={"X-Internal-Key": INTERNAL_API_KEY},
        timeout=20,
    )


@pytest.fixture(scope="module")
def vendor_world(admin_client: httpx.Client, world):
    """One device of each `device_type` at the shared fixture's location A,
    plus an employee enrolled on the `hikvision` one so hinted punches
    resolve to a real person and reach classification."""
    c = admin_client
    sfx = RUN_SUFFIX
    loc_id = world["loc_a"]["id"]

    def make_device(label, **extra):
        r = c.post("/devices", json={"location_id": loc_id, "label": f"{label} {sfx}", "is_active": True, **extra})
        assert r.status_code == 201, r.text
        return r.json()

    zkteco = make_device("QA ZK", ip_address="10.0.0.150", port=4370, device_type="zkteco")
    hikvision = make_device(
        "QA HIK", ip_address="10.0.0.151", port=80, device_type="hikvision",
        auth_username="admin", auth_password=STORED_PASSWORD,
    )
    hik_cloud = make_device(
        "QA HIKCLOUD", ip_address=CLOUD_HOST, port=443, device_type="hikvision_cloud",
        auth_username="APPKEY-QA", auth_password=STORED_PASSWORD, serial_number=f"SER{sfx}",
    )

    emp = c.post(
        "/employees",
        json={
            "location_id": loc_id,
            "employee_code": f"QA-VENDOR-{sfx}",
            "first_name": "QA",
            "last_name": "Vendor",
            "hire_date": "2025-01-01",
            "base_salary_eur": 1000.00,
            "employment_status": "active",
        },
    ).json()
    # A shift schedule is what makes classification run at all — without one
    # services/classify.py marks the whole day "unclassified" and never
    # reaches either the hint path or the parity inference.
    c.post(
        f"/employees/{emp['id']}/shift-assignments",
        json={"shift_schedule_id": world["sched_a"]["id"], "effective_from": "2025-01-01"},
    )
    hik_user_id = f"QAHIK{sfx}"
    zk_user_id = f"QAZK{sfx}"
    c.post(f"/employees/{emp['id']}/device-enrollments", json={"device_id": hikvision["id"], "device_user_id": hik_user_id})
    c.post(f"/employees/{emp['id']}/device-enrollments", json={"device_id": zkteco["id"], "device_user_id": zk_user_id})

    return {
        "zkteco": zkteco,
        "hikvision": hikvision,
        "hikvision_cloud": hik_cloud,
        "employee": emp,
        "hik_user_id": hik_user_id,
        "zk_user_id": zk_user_id,
    }


# ---------------------------------------------------------------------------
# device_type round-trips (BLUEPRINT.md 5.5)
# ---------------------------------------------------------------------------

def test_all_three_device_types_round_trip(admin_client, vendor_world):
    for key, expected_type in (
        ("zkteco", "zkteco"),
        ("hikvision", "hikvision"),
        ("hikvision_cloud", "hikvision_cloud"),
    ):
        device = vendor_world[key]
        assert device["device_type"] == expected_type
        fetched = admin_client.get(f"/devices/{device['id']}").json()
        assert fetched["device_type"] == expected_type
        assert fetched["ip_address"] == device["ip_address"]
        assert fetched["port"] == device["port"]


def test_device_type_defaults_to_zkteco_when_omitted(admin_client, world):
    """The pre-multi-vendor clients (and the existing seed data) send no
    device_type at all — that must keep meaning ZKTeco."""
    r = admin_client.post(
        "/devices",
        json={"location_id": world["loc_a"]["id"], "label": f"QA Default Type {RUN_SUFFIX}", "ip_address": "10.0.0.152", "port": 4370},
    )
    assert r.status_code == 201, r.text
    assert r.json()["device_type"] == "zkteco"


def test_unknown_device_type_rejected(admin_client, world):
    r = admin_client.post(
        "/devices",
        json={"location_id": world["loc_a"]["id"], "label": f"QA Bad Type {RUN_SUFFIX}", "ip_address": "10.0.0.153", "port": 80, "device_type": "suprema"},
    )
    assert r.status_code == 422


def test_auth_password_never_returned_by_any_device_read(admin_client, vendor_world):
    """DeviceOut/InternalDeviceOut split: the admin-facing API shows
    auth_username but never the secret."""
    device = vendor_world["hikvision"]
    detail = admin_client.get(f"/devices/{device['id']}").json()
    assert detail["auth_username"] == "admin"
    assert "auth_password" not in detail

    listed = admin_client.get("/devices", params={"location_id": device["location_id"]}).json()
    assert listed, "device list unexpectedly empty"
    for item in listed:
        assert "auth_password" not in item
    assert STORED_PASSWORD not in admin_client.get("/devices", params={"location_id": device["location_id"]}).text


# ---------------------------------------------------------------------------
# Revision 3 finding 31 — credential retargeting
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field,value",
    [("ip_address", "10.0.0.199"), ("port", 8080), ("device_type", "zkteco")],
)
def test_retargeting_a_device_without_resupplying_password_is_rejected(admin_client, vendor_world, field, value):
    device = vendor_world["hikvision"]
    r = admin_client.put(f"/devices/{device['id']}", json={field: value})
    assert r.status_code == 400
    assert "password" in r.json()["detail"].lower()

    # The row is untouched — the rejection is not a partial write.
    assert admin_client.get(f"/devices/{device['id']}").json()[field] == device[field]


def test_retargeting_with_password_succeeds_and_is_reversible(admin_client, vendor_world):
    """The legitimate flow the patch must not break: an operator who actually
    knows the device password can still move it."""
    device = vendor_world["hikvision"]
    original_ip = device["ip_address"]

    r = admin_client.put(
        f"/devices/{device['id']}",
        json={"ip_address": "10.0.0.198", "auth_password": "OperatorKnowsThis1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ip_address"] == "10.0.0.198"

    r = admin_client.put(
        f"/devices/{device['id']}",
        json={"ip_address": original_ip, "auth_password": STORED_PASSWORD},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ip_address"] == original_ip


def test_non_retargeting_edits_need_no_password(admin_client, vendor_world):
    """Renaming, toggling is_active or setting a serial touches no outbound
    target, so the guard must stay out of the way."""
    device = vendor_world["hikvision"]
    r = admin_client.put(
        f"/devices/{device['id']}",
        json={"label": f"QA HIK relabelled {RUN_SUFFIX}", "is_active": True, "serial_number": f"SN{RUN_SUFFIX}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["label"] == f"QA HIK relabelled {RUN_SUFFIX}"

    admin_client.put(f"/devices/{device['id']}", json={"label": device["label"]})


def test_resubmitting_the_same_address_is_not_a_retarget(admin_client, vendor_world):
    """A UI that PUTs the whole form back unchanged must not trip the guard."""
    device = vendor_world["hikvision"]
    r = admin_client.put(
        f"/devices/{device['id']}",
        json={"ip_address": device["ip_address"], "port": device["port"], "device_type": device["device_type"]},
    )
    assert r.status_code == 200, r.text


def test_device_with_no_stored_password_can_be_retargeted_freely(admin_client, vendor_world):
    """A ZKTeco device holds no credential, so there is nothing to harvest and
    nothing to re-supply."""
    device = vendor_world["zkteco"]
    r = admin_client.put(f"/devices/{device['id']}", json={"ip_address": "10.0.0.160"})
    assert r.status_code == 200, r.text
    admin_client.put(f"/devices/{device['id']}", json={"ip_address": device["ip_address"]})


def test_manager_cannot_retarget_another_locations_device(world, vendor_world):
    """Finding 31 was demonstrated by a plain manager. Cross-location devices
    stay entirely out of reach."""
    r = world["mgr_b"].put(f"/devices/{vendor_world['hikvision']['id']}", json={"label": "hijacked"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Revision 3 finding 31/32 — outbound target validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_host", [
    "evil.example.com/PATH-FULLY-CONTROLLED?q=1#",   # path/query/fragment takeover
    "http://evil.example.com",                        # scheme
    "user:pw@evil.example.com",                       # userinfo
    "10.0.0.1:99",                                    # embedded port
    "evil example com",                               # whitespace
])
def test_device_host_must_be_a_bare_host(admin_client, world, bad_host):
    r = admin_client.post(
        "/devices",
        json={"location_id": world["loc_a"]["id"], "label": f"QA BadHost {RUN_SUFFIX}", "ip_address": bad_host, "port": 80},
    )
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("bad_port", [0, 65536, -1])
def test_device_port_must_be_in_range(admin_client, world, bad_port):
    r = admin_client.post(
        "/devices",
        json={"location_id": world["loc_a"]["id"], "label": f"QA BadPort {RUN_SUFFIX}", "ip_address": "10.0.0.161", "port": bad_port},
    )
    assert r.status_code == 422


def test_cloud_device_host_must_be_hikvision(admin_client, world, vendor_world):
    # Create
    r = admin_client.post(
        "/devices",
        json={
            "location_id": world["loc_a"]["id"], "label": f"QA CloudBad {RUN_SUFFIX}",
            "ip_address": "attacker.example.com", "port": 443, "device_type": "hikvision_cloud",
            "auth_username": "K", "auth_password": "S",
        },
    )
    assert r.status_code == 400
    assert "hikvision open platform" in r.json()["detail"].lower()

    # Update — including the case where the password IS re-supplied, so the
    # retarget guard is satisfied and the allowlist is the only thing left.
    r = admin_client.put(
        f"/devices/{vendor_world['hikvision_cloud']['id']}",
        json={"ip_address": "attacker.example.com", "auth_password": "S"},
    )
    assert r.status_code == 400
    assert "hikvision open platform" in r.json()["detail"].lower()

    # A genuine Open Platform subdomain is accepted.
    r = admin_client.put(
        f"/devices/{vendor_world['hikvision_cloud']['id']}",
        json={"ip_address": "isgpopen.ezvizlife.com", "auth_password": STORED_PASSWORD},
    )
    assert r.status_code == 200, r.text
    admin_client.put(
        f"/devices/{vendor_world['hikvision_cloud']['id']}",
        json={"ip_address": CLOUD_HOST, "auth_password": STORED_PASSWORD},
    )


def test_flipping_a_lan_device_to_cloud_cannot_smuggle_an_arbitrary_host(admin_client, vendor_world):
    """The retarget path from finding 31 step 1: change device_type to
    hikvision_cloud while leaving ip_address pointing at an attacker host."""
    device = vendor_world["hikvision"]
    r = admin_client.put(
        f"/devices/{device['id']}",
        json={"device_type": "hikvision_cloud", "auth_password": "whatever"},
    )
    assert r.status_code == 400
    assert "hikvision open platform" in r.json()["detail"].lower()
    assert admin_client.get(f"/devices/{device['id']}").json()["device_type"] == "hikvision"
    admin_client.put(f"/devices/{device['id']}", json={"auth_password": STORED_PASSWORD})


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "169.254.169.254"])
def test_test_connection_refuses_loopback_and_link_local(admin_client, world, host):
    """SSRF guard (finding 32). 169.254.169.254 is the cloud-metadata
    endpoint; the ZKTeco path is guarded too, not just the HTTP ones."""
    r = admin_client.post(
        "/devices",
        json={"location_id": world["loc_a"]["id"], "label": f"QA SSRF {RUN_SUFFIX}", "ip_address": host, "port": 8000},
    )
    assert r.status_code == 201, r.text
    device_id = r.json()["id"]

    r = admin_client.post(f"/devices/{device_id}/test-connection")
    assert r.status_code == 200
    body = r.json()
    assert body["reachable"] is False
    assert "not a permitted device address" in body["detail"]

    admin_client.delete(f"/devices/{device_id}")


def test_test_connection_error_detail_never_echoes_the_url(admin_client, vendor_world):
    """Finding 32's second half: `str(exc)` carried the full constructed URL
    and the exact transport error, turning this into a network probe. The
    detail must now be a failure *class* only.

    All three vendors are covered, each pointed at an address that cannot
    answer — the cloud one at a non-existent Hik-Connect subdomain, so the
    allowlist is satisfied without this suite firing bogus credentials at
    Hikvision's production Open Platform.
    """
    cloud = vendor_world["hikvision_cloud"]
    admin_client.put(
        f"/devices/{cloud['id']}",
        json={"ip_address": f"qa-nonexistent-{RUN_SUFFIX}.hik-connect.com", "auth_password": STORED_PASSWORD},
    )
    try:
        for key in ("zkteco", "hikvision", "hikvision_cloud"):
            device = admin_client.get(f"/devices/{vendor_world[key]['id']}").json()
            r = admin_client.post(f"/devices/{device['id']}/test-connection")
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["reachable"] is False
            detail = body["detail"] or ""
            assert "http://" not in detail.lower()
            assert "https://" not in detail.lower()
            assert "/ISAPI/" not in detail
            assert "/api/lapp/" not in detail
            assert device["ip_address"] not in detail
    finally:
        admin_client.put(
            f"/devices/{cloud['id']}",
            json={"ip_address": CLOUD_HOST, "auth_password": STORED_PASSWORD},
        )


# ---------------------------------------------------------------------------
# Revision 3 finding 36 — punch_type_hint
# ---------------------------------------------------------------------------

def _punch_at(local_dt, device, device_user_id, raw_status_code, hint=None):
    punch = {
        "device_id": device["id"],
        "device_user_id": device_user_id,
        "punch_timestamp": local_dt.astimezone(ZoneInfo("UTC")).isoformat(),
        "raw_status_code": raw_status_code,
    }
    if hint is not None:
        punch["punch_type_hint"] = hint
    return punch


def test_punch_type_hint_bypasses_classification_inference(admin_client, vendor_world, world):
    """The point of the feature (BLUEPRINT.md 5.5): a vendor that classifies
    its own events is trusted directly.

    Proven by sending a sequence the ZKTeco heuristic would classify
    *differently*: four punches that alternate in/out/in/out by parity, but
    hinted as in/in/out/out. If the hint were ignored, punch #2 would come
    back as check_out_work.
    """
    tz = ZoneInfo("Europe/Tirane")
    day = world["monday"] + timedelta(days=1)
    device = vendor_world["hikvision"]
    uid = vendor_world["hik_user_id"]

    punches = [
        _punch_at(datetime(day.year, day.month, day.day, 9, 0, tzinfo=tz), device, uid, 0, "check_in_work"),
        _punch_at(datetime(day.year, day.month, day.day, 10, 0, tzinfo=tz), device, uid, 0, "check_in_work"),
        _punch_at(datetime(day.year, day.month, day.day, 16, 0, tzinfo=tz), device, uid, 1, "check_out_work"),
        _punch_at(datetime(day.year, day.month, day.day, 17, 0, tzinfo=tz), device, uid, 1, "check_out_work"),
    ]
    r = _ingest(punches)
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 4

    logs = admin_client.get(
        "/attendance/logs",
        params={"employee_id": vendor_world["employee"]["id"], "device_id": device["id"], "date_from": str(day), "date_to": str(day), "page_size": 100},
    ).json()["items"]
    by_time = sorted(logs, key=lambda l: l["punch_timestamp"])
    assert [l["punch_type"] for l in by_time] == [
        "check_in_work", "check_in_work", "check_out_work", "check_out_work"
    ], "punch_type_hint was overridden by the alternating-parity inference"


def test_unhinted_zkteco_punches_still_use_parity_inference(admin_client, vendor_world, world):
    """The contrast case: the same in/in/out/out *shape* with no hint goes
    through services/classify.py and comes back alternating."""
    tz = ZoneInfo("Europe/Tirane")
    day = world["monday"] + timedelta(days=4)
    device = vendor_world["zkteco"]
    uid = vendor_world["zk_user_id"]

    punches = [
        _punch_at(datetime(day.year, day.month, day.day, 9, 0, tzinfo=tz), device, uid, 0),
        _punch_at(datetime(day.year, day.month, day.day, 10, 0, tzinfo=tz), device, uid, 0),
        _punch_at(datetime(day.year, day.month, day.day, 16, 0, tzinfo=tz), device, uid, 0),
        _punch_at(datetime(day.year, day.month, day.day, 17, 0, tzinfo=tz), device, uid, 0),
    ]
    r = _ingest(punches)
    assert r.status_code == 200, r.text

    logs = admin_client.get(
        "/attendance/logs",
        params={"employee_id": vendor_world["employee"]["id"], "device_id": device["id"], "date_from": str(day), "date_to": str(day), "page_size": 100},
    ).json()["items"]
    by_time = sorted(logs, key=lambda l: l["punch_timestamp"])
    assert [l["punch_type"] for l in by_time] == [
        "check_in_work", "check_out_work", "check_in_work", "check_out_work"
    ]


def test_hinted_punch_flows_through_to_daily_status(admin_client, vendor_world, world):
    """Hint -> classification -> daily status: the hinted first-in/last-out
    pair is what drives late minutes, overtime and the dashboard."""
    day = world["monday"] + timedelta(days=1)
    r = admin_client.get(
        "/attendance/daily-status",
        params={"employee_id": vendor_world["employee"]["id"], "date_from": str(day), "date_to": str(day)},
    )
    assert r.status_code == 200, r.text
    row = r.json()["items"][0]
    assert row["actual_first_in"] is not None
    assert row["actual_last_out"] is not None
    assert row["actual_last_out"] != row["actual_first_in"]
    assert row["status"] in ("present", "late")


def test_punch_type_hint_rejected_for_zkteco_device(vendor_world):
    """Finding 36: ZKTeco reports a bare numeric status code and its adapter
    never sets a hint, so a hint on one of its punches can only come from a
    caller trying to dictate payroll-relevant classification."""
    r = _ingest([{
        "device_id": vendor_world["zkteco"]["id"],
        "device_user_id": vendor_world["zk_user_id"],
        "punch_timestamp": "2026-09-01T08:00:00+00:00",
        "raw_status_code": 0,
        "punch_type_hint": "check_in_work",
    }])
    assert r.status_code == 400, r.text
    assert "does not self-classify" in r.json()["detail"]


def test_punch_type_hint_accepted_for_both_hikvision_transports(vendor_world):
    for key in ("hikvision", "hikvision_cloud"):
        r = _ingest([{
            "device_id": vendor_world[key]["id"],
            "device_user_id": f"UNENROLLED-{key}-{RUN_SUFFIX}",
            "punch_timestamp": "2026-09-01T08:30:00+00:00",
            "raw_status_code": 0,
            "punch_type_hint": "check_in_work",
        }])
        assert r.status_code == 200, f"{key}: {r.text}"
        assert r.json()["inserted"] == 1


def test_rejected_hint_does_not_partially_write_the_batch(admin_client, vendor_world):
    """The zkteco hint check runs per-punch and raises — a mixed batch must
    not leave the legitimate punches behind."""
    hik = vendor_world["hikvision"]
    zk = vendor_world["zkteco"]
    marker = f"BATCH{RUN_SUFFIX}"
    r = _ingest([
        {"device_id": hik["id"], "device_user_id": marker, "punch_timestamp": "2026-09-02T08:00:00+00:00", "raw_status_code": 0, "punch_type_hint": "check_in_work"},
        {"device_id": zk["id"], "device_user_id": marker, "punch_timestamp": "2026-09-02T08:01:00+00:00", "raw_status_code": 0, "punch_type_hint": "check_in_work"},
    ])
    assert r.status_code == 400

    stored = _compose_exec_python(
        f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
print(db.execute(text("SELECT count(*) FROM attendance_logs WHERE device_user_id = :u"), {{"u": {marker!r}}}).scalar())
db.close()
"""
    )
    assert stored == "0", f"partial batch written: {stored} rows"


def test_punch_type_hint_value_is_constrained(vendor_world):
    r = _ingest([{
        "device_id": vendor_world["hikvision"]["id"],
        "device_user_id": vendor_world["hik_user_id"],
        "punch_timestamp": "2026-09-03T08:00:00+00:00",
        "raw_status_code": 0,
        "punch_type_hint": "unclassified",
    }])
    assert r.status_code == 422


def test_ingest_still_requires_the_internal_key(vendor_world):
    r = httpx.post(
        f"{API_BASE_URL}/internal/ingest/punches",
        json={"punches": [{
            "device_id": vendor_world["hikvision"]["id"],
            "device_user_id": vendor_world["hik_user_id"],
            "punch_timestamp": "2026-09-04T08:00:00+00:00",
            "raw_status_code": 0,
            "punch_type_hint": "check_in_work",
        }]},
        timeout=15,
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Revision 3 finding 37 — device-enrollment location scoping
# ---------------------------------------------------------------------------

def test_enrollment_validates_the_devices_location_not_just_the_employees(world, vendor_world, admin_client):
    """A manager could bind their own employee to another location's reader,
    capturing that reader's traffic into their own payroll."""
    mgr_b = world["mgr_b"]
    emp_b = world["emp_b"]

    # mgr_b owns emp_b, but the hikvision device belongs to location A.
    r = mgr_b.post(
        f"/employees/{emp_b['id']}/device-enrollments",
        json={"device_id": vendor_world["hikvision"]["id"], "device_user_id": f"XLOC{RUN_SUFFIX}"},
    )
    assert r.status_code == 403
    assert vendor_world["hikvision"]["label"] not in r.text  # no cross-tenant label leak


def test_enrollment_on_a_nonexistent_device_is_a_clean_400(admin_client, world):
    """Used to surface as a raw FK-violation 500."""
    r = admin_client.post(
        f"/employees/{world['emp_a']['id']}/device-enrollments",
        json={"device_id": 999999999, "device_user_id": f"GHOST{RUN_SUFFIX}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "Device not found"


# ---------------------------------------------------------------------------
# Revision 3 finding 34 — config location scoping (regression against
# Revision 2 finding 28)
# ---------------------------------------------------------------------------

def test_manager_cannot_move_own_config_to_another_location(world, admin_client):
    mgr_a = world["mgr_a"]
    cfg = mgr_a.post(
        "/config/penalty",
        json={
            "location_id": world["loc_a"]["id"],
            "rule_type": "threshold_allowance",
            "allowance_minutes": 10,
            "flat_amount_eur": 5.00,
            "effective_from": "2026-01-01",
        },
    )
    assert cfg.status_code == 201, cfg.text
    cfg = cfg.json()

    try:
        # Editing it inside their own location still works — the patch must
        # not break the manager-write model.
        r = mgr_a.put(f"/config/penalty/{cfg['id']}", json={"flat_amount_eur": 7.50})
        assert r.status_code == 200, r.text
        assert r.json()["flat_amount_eur"] == 7.50

        # Moving it to another location does not.
        r = mgr_a.put(f"/config/penalty/{cfg['id']}", json={"location_id": world["loc_b"]["id"], "rate_per_minute_eur": 99.99})
        assert r.status_code == 403
        assert r.json()["detail"] == "Not your location"

        # Neither does promoting it org-wide (location_id null is the global
        # scope services/config_lookup.py falls back to).
        r = mgr_a.put(f"/config/penalty/{cfg['id']}", json={"location_id": None, "flat_amount_eur": 500.00})
        assert r.status_code == 403

        # Nothing leaked through.
        after = admin_client.get(f"/config/penalty/{cfg['id']}").json()
        assert after["location_id"] == world["loc_a"]["id"]
        assert after["flat_amount_eur"] == 7.50

        # An admin performing the same move is still allowed.
        r = admin_client.put(f"/config/penalty/{cfg['id']}", json={"location_id": world["loc_b"]["id"]})
        assert r.status_code == 200, r.text
        assert r.json()["location_id"] == world["loc_b"]["id"]
    finally:
        _compose_exec_python(
            f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM penalty_config WHERE id = :i"), {{"i": {cfg['id']!r}}})
db.commit()
db.close()
"""
        )


def test_manager_cannot_move_overtime_or_absence_config_either(world, admin_client):
    """All three config update endpoints shared the defect; all three were
    patched, so all three are checked."""
    mgr_a = world["mgr_a"]
    loc_a, loc_b = world["loc_a"]["id"], world["loc_b"]["id"]

    ot = mgr_a.post(
        "/config/overtime",
        json={"location_id": loc_a, "threshold_basis": "daily", "daily_threshold_minutes": 30, "rate_per_hour_eur": 10.00, "effective_from": "2026-01-01"},
    )
    assert ot.status_code == 201, ot.text
    ot = ot.json()

    ar = mgr_a.post(
        "/config/absence-rule",
        json={"location_id": loc_a, "deduction_basis": "full_day_salary_fraction", "deduction_value": 1.0, "effective_from": "2026-01-01"},
    )
    assert ar.status_code == 201, ar.text
    ar = ar.json()

    try:
        assert mgr_a.put(f"/config/overtime/{ot['id']}", json={"location_id": loc_b}).status_code == 403
        assert mgr_a.put(f"/config/overtime/{ot['id']}", json={"location_id": None, "rate_per_hour_eur": 500}).status_code == 403
        assert mgr_a.put(f"/config/absence-rule/{ar['id']}", json={"location_id": loc_b}).status_code == 403
        assert mgr_a.put(f"/config/absence-rule/{ar['id']}", json={"location_id": None}).status_code == 403

        # Same-location edits keep working.
        assert mgr_a.put(f"/config/overtime/{ot['id']}", json={"rate_per_hour_eur": 12.00}).status_code == 200
        assert mgr_a.put(f"/config/absence-rule/{ar['id']}", json={"deduction_value": 0.5}).status_code == 200
    finally:
        _compose_exec_python(
            f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM overtime_config WHERE id = :i"), {{"i": {ot['id']!r}}})
db.execute(text("DELETE FROM absence_rule_config WHERE id = :i"), {{"i": {ar['id']!r}}})
db.commit()
db.close()
"""
        )


def test_location_specific_config_beats_org_wide_config(admin_client, world):
    """services/config_lookup.py's documented rule — a location-specific row
    outranks a location_id-null one on the same date.

    Regression test for the inverted ordering found during this QA pass:
    `(location_id = :loc) DESC` is NULL for an org-wide row and Postgres
    sorts DESC as NULLS FIRST, so the org-wide row won and every
    location-specific pay rule was silently ignored.
    """
    loc_id = world["loc_a"]["id"]
    on_date = str(world["monday"])

    # Plant a competing org-wide row effective the same day, so the test
    # actually exercises the contention instead of passing by default.
    org_wide_id = int(
        _compose_exec_python(
            f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
rid = db.execute(text(
    "INSERT INTO penalty_config (location_id, rule_type, allowance_minutes, flat_amount_eur, "
    "early_departure_rate_per_minute_eur, effective_from, is_active) "
    "VALUES (NULL, 'threshold_allowance', 0, 999.00, 9.99, :d, true) RETURNING id"
), {{"d": {on_date!r}}}).scalar()
db.commit()
print(rid)
db.close()
"""
        )
    )

    try:
        picked = _compose_exec_python(
            f"""
import datetime
from app.database import SessionLocal
from app.models import PenaltyConfig
from app.services.config_lookup import get_effective_config
db = SessionLocal()
row = get_effective_config(db, PenaltyConfig, {loc_id!r}, datetime.date.fromisoformat({on_date!r}))
print(row.location_id if row is not None else "NONE")
db.close()
"""
        )
        assert picked == str(loc_id), (
            f"org-wide config {org_wide_id} outranked the location-specific one "
            f"(picked location_id={picked}) — location-scoped pay rules are being ignored"
        )
    finally:
        _compose_exec_python(
            f"""
from app.database import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text("DELETE FROM penalty_config WHERE id = :i"), {{"i": {org_wide_id!r}}})
db.commit()
db.close()
"""
        )
