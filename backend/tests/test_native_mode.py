"""Native (non-Docker) mode — the topology the Windows install runs.

There is no nginx on the Windows install, so the server takes over nginx's two
jobs: serving the web UI, and keeping /api/v1/internal/ reachable only from
this same machine. These tests drive the native entry points through
docker-compose.native-test.yml, where:

  * requests from this test process arrive at the server from a non-loopback
    address — standing in for a PC on the client's LAN;
  * the native worker shares the server's network namespace, so the two talk
    over real loopback, as they will on one Windows PC.

Skipped when that harness isn't running.
"""
import re
import subprocess

import httpx
import pytest

from conftest import COMPOSE_DIR, RUN_SUFFIX, _compose_exec_python

NATIVE = "http://127.0.0.1:8001"
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.native-test.yml"]

try:
    httpx.get(f"{NATIVE}/health", timeout=3)
except httpx.HTTPError:
    pytest.skip("native-mode harness not running (see docker-compose.native-test.yml)", allow_module_level=True)

INTERNAL_API_KEY = _compose_exec_python("from app.config import settings; print(settings.internal_api_key)")


def _in_server_container(code: str) -> str:
    """Runs Python inside api-native — i.e. a caller on the same machine."""
    result = subprocess.run(
        COMPOSE + ["exec", "-T", "api-native", "python", "-c", code],
        cwd=COMPOSE_DIR,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


@pytest.fixture(scope="module")
def native_admin(admin_client, qa_username, qa_password):
    """Same QA admin account, logged in through the native server."""
    client = httpx.Client(base_url=f"{NATIVE}/api/v1", timeout=60)
    r = client.post("/auth/login", json={"username": qa_username, "password": qa_password})
    assert r.status_code == 204, r.text
    yield client
    client.close()


# ---------------------------------------------------------------------------
# The web UI, served by the API itself
# ---------------------------------------------------------------------------

def test_the_app_is_served_at_the_root():
    r = httpx.get(f"{NATIVE}/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<title>Chronos</title>" in r.text


def test_a_deep_link_loads_the_app_so_refresh_works():
    """nginx's `try_files ... /index.html`: refreshing /employees/12 must load
    the app, not return a 404."""
    r = httpx.get(f"{NATIVE}/employees/12")
    assert r.status_code == 200
    assert "<title>Chronos</title>" in r.text


def test_real_files_are_served_as_themselves():
    manual = httpx.get(f"{NATIVE}/manuali.html")
    assert manual.status_code == 200
    assert "Manuali i Chronos" in manual.text

    icon = httpx.get(f"{NATIVE}/favicon.svg")
    assert icon.status_code == 200
    assert "image/svg+xml" in icon.headers["content-type"]


def test_the_built_javascript_bundle_is_served():
    index = httpx.get(f"{NATIVE}/").text
    script = re.search(r'src="(/assets/[^"]+\.js)"', index)
    assert script, "index.html references no /assets/*.js bundle"
    r = httpx.get(f"{NATIVE}{script.group(1)}")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_an_unknown_api_path_is_a_json_404_not_the_app_shell():
    """Otherwise a typo'd API call would come back as HTML with a 200 and the
    frontend would misreport it."""
    r = httpx.get(f"{NATIVE}/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", [
    "/..%2F..%2F..%2Fetc%2Fpasswd",
    "/%2E%2E/%2E%2E/%2E%2E/etc/passwd",
    "/assets/..%2F..%2F..%2Fetc%2Fpasswd",
])
def test_path_traversal_cannot_read_files_outside_the_build(path):
    r = httpx.get(f"{NATIVE}{path}")
    assert "root:" not in r.text


# ---------------------------------------------------------------------------
# Internal endpoints: this machine only
# ---------------------------------------------------------------------------

def test_internal_endpoints_are_invisible_from_the_network():
    """Same 404 nginx gives in the Docker deployment — even with the correct
    key, because a leaked key alone must not be enough."""
    r = httpx.get(f"{NATIVE}/api/v1/internal/devices", headers={"X-Internal-Key": INTERNAL_API_KEY})
    assert r.status_code == 404


def test_a_forwarded_header_cannot_impersonate_loopback():
    r = httpx.get(
        f"{NATIVE}/api/v1/internal/devices",
        headers={"X-Internal-Key": INTERNAL_API_KEY, "X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"},
    )
    assert r.status_code == 404


def test_internal_endpoints_answer_this_machine():
    status = _in_server_container(
        "import urllib.request\n"
        "from app.config import settings\n"
        "req = urllib.request.Request('http://127.0.0.1:8080/api/v1/internal/devices',"
        " headers={'X-Internal-Key': settings.internal_api_key})\n"
        "print(urllib.request.urlopen(req).status)\n"
    )
    assert status == "200"


def test_the_worker_is_not_listening_on_the_network():
    """Its only endpoint triggers device syncs; on Windows it must be
    reachable from the server on the same PC and nothing else."""
    listening = _in_server_container(
        "import socket\n"
        "ip = socket.gethostbyname(socket.gethostname())\n"
        "s = socket.socket(); s.settimeout(2)\n"
        "print('open' if s.connect_ex((ip, 8100)) == 0 else 'closed')\n"
    )
    assert listening == "closed"


# ---------------------------------------------------------------------------
# The whole loop, end to end
# ---------------------------------------------------------------------------

def test_login_and_the_api_work_through_the_native_server(native_admin, qa_username):
    me = native_admin.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == qa_username


def test_sync_now_round_trips_between_server_and_worker_over_loopback(native_admin, world):
    """Sync now: server -> worker (127.0.0.1:8100) -> server's internal
    endpoints (loopback, so allowed) -> device. The device here does not
    exist, so the worker reports a device error — but getting that report
    back at all proves both loopback legs. If either were blocked the
    server would answer 502."""
    device = native_admin.post(
        "/devices",
        json={
            "location_id": world["loc_a"]["id"],
            "label": f"QA Native Sync {RUN_SUFFIX}",
            # Hikvision rather than ZKTeco: an unreachable Hikvision fails in
            # ~15s, inside the server's 30s wait for the worker. An unreachable
            # ZKTeco takes 30s (pyzk retries), which hits that wait exactly —
            # a separate issue, see BACKEND_NOTES.
            "device_type": "hikvision",
            "ip_address": "10.255.255.1",
            "port": 80,
            "auth_username": "admin",
            "auth_password": "DevicePw123",
            "is_active": True,
        },
    )
    assert device.status_code == 201, device.text

    r = native_admin.post(f"/devices/{device.json()['id']}/sync")
    assert r.status_code == 202, r.text  # the sync route answers 202 Accepted
    body = r.json()
    assert body["device_id"] == device.json()["id"]
    assert "error" in body, "an unreachable device should be reported, not silently synced"
