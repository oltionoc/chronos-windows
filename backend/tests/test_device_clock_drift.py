"""Device clock drift, API side — worker reports it, alerts surface it.

Every punch carries the timestamp the DEVICE wrote, so a terminal whose
clock has drifted produces lateness and overtime wrong by exactly that
drift, invisibly. This happened on real hardware: a DS-K1T804AMF still on
its factory UTC+8 stamped events `+08:00` and turned an on-time arrival into
61 minutes late. The adapter half (reading the device clock) is covered in
test_device_adapters.py; this covers what the API does with the reading.
"""
import httpx
import pytest

from conftest import API_BASE_URL, RUN_SUFFIX, _compose_exec_python

INTERNAL_API_KEY = _compose_exec_python(
    "from app.config import settings; print(settings.internal_api_key)"
)


def _heartbeat(device_id: int, body: dict | None):
    return httpx.patch(
        f"{API_BASE_URL}/internal/devices/{device_id}/heartbeat",
        json=body,
        headers={"X-Internal-Key": INTERNAL_API_KEY},
        timeout=15,
    )


@pytest.fixture(scope="module")
def clock_device(admin_client: httpx.Client, world):
    return admin_client.post(
        "/devices",
        json={
            "location_id": world["loc_a"]["id"],
            "label": f"QA Clock Device {RUN_SUFFIX}",
            "device_type": "hikvision",
            "ip_address": "10.0.0.245",
            "port": 80,
            "auth_username": "admin",
            "auth_password": "DevicePw123",
            "is_active": True,
        },
    ).json()


def _device(admin_client, device_id):
    r = admin_client.get(f"/devices/{device_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _drift_alerts(admin_client, label):
    alerts = admin_client.get("/reports/alerts", params={"days": 7}).json()["alerts"]
    return [a for a in alerts if a["type"] == "device_clock_drift" and a["device_label"] == label]


def test_heartbeat_records_the_reading(admin_client, clock_device):
    assert _heartbeat(clock_device["id"], {"clock_skew_seconds": 12}).status_code == 204
    row = _device(admin_client, clock_device["id"])
    assert row["clock_skew_seconds"] == 12
    assert row["clock_checked_at"] is not None
    assert row["last_synced_at"] is not None


def test_small_drift_raises_nothing(admin_client, clock_device):
    """Under the tolerance the error is smaller than any grace period and
    cannot flip a lateness decision, so it is noise, not an alert."""
    _heartbeat(clock_device["id"], {"clock_skew_seconds": 45})
    assert _drift_alerts(admin_client, clock_device["label"]) == []


def test_timezone_sized_drift_is_a_danger_alert(admin_client, clock_device):
    _heartbeat(clock_device["id"], {"clock_skew_seconds": 8 * 3600})
    alerts = _drift_alerts(admin_client, clock_device["label"])
    assert len(alerts) == 1, "a device 8h out must be surfaced"
    assert alerts[0]["severity"] == "danger"
    assert alerts[0]["count"] == 480  # minutes ahead, signed


def test_a_device_behind_the_server_is_also_flagged(admin_client, clock_device):
    _heartbeat(clock_device["id"], {"clock_skew_seconds": -600})
    alerts = _drift_alerts(admin_client, clock_device["label"])
    assert len(alerts) == 1
    assert alerts[0]["count"] == -10


def test_a_sync_that_could_not_read_the_clock_keeps_the_last_reading(admin_client, clock_device):
    """A vendor with no clock endpoint (Hik-Connect) or a failed read must not
    overwrite a real measurement with "unknown" — otherwise one bad read
    silently clears a live alert."""
    before = _device(admin_client, clock_device["id"])
    assert before["clock_skew_seconds"] == -600

    assert _heartbeat(clock_device["id"], {"clock_skew_seconds": None}).status_code == 204
    after = _device(admin_client, clock_device["id"])
    assert after["clock_skew_seconds"] == -600
    assert after["clock_checked_at"] == before["clock_checked_at"]
    assert after["last_synced_at"] != before["last_synced_at"], "the sync itself still counts"


def test_heartbeat_still_works_with_no_body_at_all(admin_client, clock_device):
    """Backwards compatibility: a worker from before this feature sends an
    empty PATCH, and must not start failing its heartbeat."""
    assert _heartbeat(clock_device["id"], None).status_code == 204
    assert _device(admin_client, clock_device["id"])["clock_skew_seconds"] == -600


def test_clock_reading_is_never_exposed_without_authentication(clock_device):
    r = httpx.get(f"{API_BASE_URL}/devices/{clock_device['id']}", timeout=15)
    assert r.status_code == 401
