"""Test Connection reports the device clock.

Someone running Test Connection is standing in front of the device, which is
the one moment where "your clock is 8 hours out" can be acted on immediately.
Before this, the only way to get a clock reading was to wait for a worker
sync, so a freshly installed device showed "Not measured" with no way to
measure it.

The message text is asserted inside the api container (the helper is pure),
and the stored-reading behaviour is asserted over HTTP.
"""
import httpx
import pytest

from conftest import RUN_SUFFIX, _compose_exec_python


def _detail(skew: str) -> str:
    return _compose_exec_python(
        "from app.routers.devices import _reachable_detail; "
        f"print(_reachable_detail({skew}))"
    )


def test_a_device_with_no_readable_clock_says_nothing_about_it():
    """Hik-Connect and any firmware that reports an unanchored local time fall
    here — silence beats inventing a reading."""
    assert _detail("None") == "Connected successfully"


def test_a_clock_within_tolerance_is_reported_as_matching():
    assert "matches the server" in _detail("45")


def test_a_drifted_clock_is_called_out_with_its_size_and_direction():
    ahead = _detail("8 * 3600")
    assert "480 minute(s) ahead of" in ahead
    assert "wrong" in ahead

    behind = _detail("-600")
    assert "10 minute(s) behind" in behind


def test_tolerance_matches_the_alert_threshold():
    """Two places decide whether a clock is acceptable: this endpoint and the
    alerts feed. If they disagree, Test Connection says "fine" while Alerts
    says "danger" for the same device."""
    devices_value = _compose_exec_python(
        "from app.routers.devices import CLOCK_DRIFT_TOLERANCE_SECONDS; print(CLOCK_DRIFT_TOLERANCE_SECONDS)"
    )
    reports_value = _compose_exec_python(
        "from app.routers.reports import CLOCK_DRIFT_TOLERANCE_SECONDS; print(CLOCK_DRIFT_TOLERANCE_SECONDS)"
    )
    assert devices_value == reports_value


def test_an_unreachable_device_stores_no_reading(admin_client: httpx.Client, world):
    """A failed connection must not overwrite a good previous measurement with
    a guess, and must not blank it either."""
    device = admin_client.post(
        "/devices",
        json={
            "location_id": world["loc_a"]["id"],
            "label": f"QA Unreachable {RUN_SUFFIX}",
            "device_type": "hikvision",
            "ip_address": "10.255.255.1",  # routable-looking, nothing there
            "port": 80,
            "auth_username": "admin",
            "auth_password": "DevicePw123",
            "is_active": True,
        },
    ).json()

    r = admin_client.post(f"/devices/{device['id']}/test-connection")
    assert r.status_code == 200, r.text
    assert r.json()["reachable"] is False

    after = admin_client.get(f"/devices/{device['id']}").json()
    assert after["clock_skew_seconds"] is None
    assert after["clock_checked_at"] is None
