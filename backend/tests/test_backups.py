"""Backup health surfacing — a backup nobody checks is a backup nobody has.

The dump itself runs in its own container (ops/backup.sh) and writes
`LAST_BACKUP` after every attempt; `api` mounts that folder read-only. These
tests drive the marker file directly and assert the alert an admin would see,
because the failure being guarded against is silence: on-premise there is one
machine holding every punch and every payroll run, and a backup that quietly
stopped working is discovered on the day it is needed.

Each test restores the marker it found, so the live stack is left exactly as
it was.
"""
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from conftest import COMPOSE_DIR

MARKER_PATH = "/backups/LAST_BACKUP"


def _backup_exec(command: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    """Runs a shell command inside the `backup` container.

    The marker is written by that container running as root, so the host test
    user cannot edit it directly — and making the backups world-writable to
    suit a test would be the wrong trade. Same "drive the real stack" approach
    conftest.py already uses for the `api` container."""
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "backup", "sh", "-c", command],
        cwd=COMPOSE_DIR,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _alerts(admin_client, *types):
    # Assert the response before reading it: auth.py rate-limits per account,
    # so a burst of bad logins from another test module can briefly turn this
    # into an error body. Without this check that surfaces as a bare KeyError
    # on "alerts" and looks like a backup bug.
    r = admin_client.get("/reports/alerts", params={"days": 7})
    assert r.status_code == 200, f"alerts request failed: {r.status_code} {r.text[:200]}"
    return [a for a in r.json()["alerts"] if a["type"] in types]


@pytest.fixture
def marker():
    """Writes the marker for one test and puts back whatever was there."""
    probe = _backup_exec(f"cat {MARKER_PATH} 2>/dev/null || true")
    if probe.returncode != 0:
        pytest.skip("backup service is not running in this stack")
    original = probe.stdout or None

    def write(content: str | None):
        if content is None:
            result = _backup_exec(f"rm -f {MARKER_PATH}")
        else:
            result = _backup_exec(f"cat > {MARKER_PATH}", stdin=content)
        assert result.returncode == 0, result.stderr

    yield write

    write(original)


def _stamp(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


BACKUP_TYPES = ("backup_missing", "backup_failed", "backup_stale")


def test_a_recent_successful_backup_raises_nothing(admin_client, marker):
    marker(f"{_stamp(1)} ok chronos-test.dump\n")
    assert _alerts(admin_client, *BACKUP_TYPES) == []


def test_a_failed_backup_is_a_danger_alert(admin_client, marker):
    marker(f"{_stamp(1)} failed -\n")
    alerts = _alerts(admin_client, *BACKUP_TYPES)
    assert [a["type"] for a in alerts] == ["backup_failed"]
    assert alerts[0]["severity"] == "danger"


def test_an_old_backup_is_flagged_even_though_it_succeeded(admin_client, marker):
    """Succeeded two days ago and nothing since: the schedule has stopped, or
    the machine has been off long enough to matter."""
    marker(f"{_stamp(50)} ok chronos-test.dump\n")
    alerts = _alerts(admin_client, *BACKUP_TYPES)
    assert [a["type"] for a in alerts] == ["backup_stale"]
    assert alerts[0]["count"] >= 36


def test_one_missed_night_is_tolerated(admin_client, marker):
    """A daily schedule plus a single missed run is normal operation on a PC
    that gets switched off; alerting there would train people to ignore it."""
    marker(f"{_stamp(30)} ok chronos-test.dump\n")
    assert _alerts(admin_client, *BACKUP_TYPES) == []


def test_no_marker_at_all_is_the_loudest_case(admin_client, marker):
    """The backup service was never started. Nothing else in the app would
    ever mention it, which is exactly why it is an alert."""
    marker(None)
    alerts = _alerts(admin_client, *BACKUP_TYPES)
    assert [a["type"] for a in alerts] == ["backup_missing"]
    assert alerts[0]["severity"] == "danger"


def test_a_garbled_marker_is_treated_as_a_failure_not_ignored(admin_client, marker):
    marker("something unexpected\n")
    assert [a["type"] for a in _alerts(admin_client, *BACKUP_TYPES)] == ["backup_failed"]


def test_managers_do_not_see_backup_alerts(world, marker):
    """Infrastructure health is an admin concern; a location manager can do
    nothing about it and has no business knowing the server's state."""
    marker(f"{_stamp(100)} failed -\n")
    rows = world["mgr_a"].get("/reports/alerts", params={"days": 7}).json()["alerts"]
    assert [a for a in rows if a["type"] in BACKUP_TYPES] == []
