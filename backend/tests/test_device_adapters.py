"""Vendor-adapter coverage — worker/worker/adapters/, BLUEPRINT.md 5.5.

Neither Hikvision transport can be pointed at real hardware (the client has
none available to us), so this module covers the two things that do not need
a device:

  * the pure parsing/mapping layer — attendanceStatus -> punch_type_hint,
    the raw_status_code encoding, the envelope checks, and the "raise rather
    than silently drop a punch" behaviour the cloud adapter documents;
  * the guard rails added in SECURITY_REPORT.md Revision 3 — bare-host /
    port validation, the Hik-Connect host allowlist, and the MAX_PAGES /
    MAX_PUNCHES / MAX_RESPONSE_BYTES caps that stop one misbehaving device
    wedging the whole worker (its scheduled job is max_instances=1).

The paging caps are exercised against a REAL HTTP server (stdlib
http.server, bound to this machine's own private-LAN address) rather than a
transport mock, keeping to the project's "real stack, no mocks" convention —
and because binding it on loopback would be refused by the very guard under
test. `worker` shares no package with `backend`, so its source directory is
put on sys.path directly; nothing here touches the database or the API.
"""
import ipaddress
import json
import socket
import socketserver
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest

WORKER_SRC = Path(__file__).resolve().parents[2] / "worker"
if str(WORKER_SRC) not in sys.path:
    sys.path.insert(0, str(WORKER_SRC))

from worker.adapters import _target, hikvision, hikvision_cloud  # noqa: E402


def _private_lan_address() -> str | None:
    """An address on this host that the adapters' guard will accept: a real
    private (RFC1918) address, which is exactly where a LAN attendance
    device lives. Loopback is deliberately unusable here — that is the guard
    working, so the stub server has to sit somewhere else."""
    candidates = []
    try:
        candidates += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    # The hostname often resolves only to 127.0.1.1 (Debian/WSL default).
    # Asking the routing table which source address it would use for an
    # off-link destination gives the real interface address without sending
    # anything (UDP connect() is local-only).
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1, RFC 5737
        candidates.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()

    for candidate in candidates:
        addr = ipaddress.ip_address(candidate)
        if addr.is_private and not addr.is_loopback and not addr.is_link_local:
            return str(addr)
    return None


LAN_ADDRESS = _private_lan_address()


# ---------------------------------------------------------------------------
# Outbound-target guard (finding 32) — worker's own copy of the rules
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad", [
    "device.local/PATH?q=1#",
    "http://device.local",
    "user:pw@device.local",
    "10.0.0.1:4370",
    "device local",
    "",
    None,
])
def test_safe_host_rejects_anything_that_could_rewrite_the_url(bad):
    with pytest.raises(ValueError):
        _target.safe_host(bad)


@pytest.mark.parametrize("good", ["10.0.0.5", "192.168.1.20", "terminal-01.example.com", "2001:db8::1"])
def test_safe_host_accepts_bare_hosts(good):
    assert _target.safe_host(good) == good


@pytest.mark.parametrize("forbidden", ["127.0.0.1", "localhost", "169.254.169.254", "0.0.0.0"])
def test_safe_host_rejects_loopback_link_local_and_unspecified(forbidden):
    with pytest.raises(ValueError):
        _target.safe_host(forbidden)


def test_safe_host_allows_private_ranges():
    """Explicitly NOT blocked — a real LAN device lives there (the documented
    residual risk in finding 32)."""
    assert _target.safe_host("192.168.4.7") == "192.168.4.7"


@pytest.mark.parametrize("bad_port", [0, 65536, -1])
def test_safe_port_range(bad_port):
    with pytest.raises(ValueError):
        _target.safe_port(bad_port)


@pytest.mark.parametrize("host", [
    "open.hik-connect.com",
    "hik-connect.com",
    "isgpopen.ezvizlife.com",
    "open.ys7.com",
    "api.hikvision.com",
])
def test_safe_cloud_host_accepts_open_platform_hosts(host):
    assert _target.safe_cloud_host(host) == host


@pytest.mark.parametrize("host", [
    "attacker.example.com",
    "hik-connect.com.attacker.example",   # suffix-confusion attempt
    "nothik-connect.com",                 # substring, not a subdomain
    "192.168.1.10",
])
def test_safe_cloud_host_rejects_everything_else(host):
    with pytest.raises(ValueError):
        _target.safe_cloud_host(host)


def test_cloud_base_url_is_always_https():
    """The scheme used to be derived from the port (80 -> http), so one
    integer edit put the appKey/appSecret on the wire in cleartext."""
    for port in (80, 443, 8080):
        url = hikvision_cloud._base_url({"ip_address": "open.hik-connect.com", "port": port})
        assert url.startswith("https://"), url
        assert url == f"https://open.hik-connect.com:{port}"


def test_cloud_base_url_refuses_a_non_hikvision_host():
    with pytest.raises(ValueError):
        hikvision_cloud._base_url({"ip_address": "attacker.example.com", "port": 443})


# ---------------------------------------------------------------------------
# Status mapping — the feature itself (BLUEPRINT.md 5.5)
# ---------------------------------------------------------------------------

def test_status_map_covers_the_documented_hikvision_vocabulary():
    assert hikvision.STATUS_MAP == {
        "checkIn": "check_in_work",
        "checkOut": "check_out_work",
        "breakIn": "check_in_break",
        "breakOut": "check_out_break",
        # Kept distinct since migration 0014: these used to fold into the work
        # pair, which discarded the device's own statement that a stretch was
        # overtime. services/recompute.py exempts badged overtime from the
        # daily overtime threshold, so the distinction is worth money.
        "overtimeIn": "check_in_overtime",
        "overtimeOut": "check_out_overtime",
    }


def test_every_mapped_hint_has_a_raw_status_code():
    """RAW_CODE is indexed with the mapped hint in both adapters; a missing
    entry would be a KeyError mid-poll."""
    for hint in set(hikvision.STATUS_MAP.values()):
        assert hint in hikvision.RAW_CODE


def test_raw_codes_match_the_zkteco_break_convention():
    """services/classify.py reads 2 as break-out and 3 as break-in; the
    Hikvision encoding has to agree or a hint-less replay would be
    reclassified wrongly."""
    assert hikvision.RAW_CODE["check_in_work"] == 0
    assert hikvision.RAW_CODE["check_out_work"] == 1
    assert hikvision.RAW_CODE["check_out_break"] == 2
    assert hikvision.RAW_CODE["check_in_break"] == 3
    # 4/5 are ZKTeco's overtime codes, which classify.py reads the same way
    # for both vendors.
    assert hikvision.RAW_CODE["check_in_overtime"] == 4
    assert hikvision.RAW_CODE["check_out_overtime"] == 5


def test_cloud_adapter_reuses_the_direct_adapters_mapping():
    """Both transports carry the same device's events, so a divergence here
    would mean the same punch classified differently depending on how it was
    fetched."""
    assert hikvision_cloud.STATUS_MAP is hikvision.STATUS_MAP
    assert hikvision_cloud.RAW_CODE is hikvision.RAW_CODE


# ---------------------------------------------------------------------------
# Cloud event parsing (_to_punch)
# ---------------------------------------------------------------------------

DEVICE = {"id": 7, "ip_address": "open.hik-connect.com", "port": 443, "serial_number": "SER1"}


def test_to_punch_maps_a_normal_event():
    punch = hikvision_cloud._to_punch(DEVICE, {
        "attendanceStatus": "checkIn",
        "employeeNoString": "E-42",
        "time": "2026-09-08T09:00:00+02:00",
    })
    assert punch == {
        "device_id": 7,
        "device_user_id": "E-42",
        "punch_timestamp": "2026-09-08T09:00:00+02:00",
        "raw_status_code": 0,
        "punch_type_hint": "check_in_work",
    }


def test_to_punch_falls_back_to_numeric_employee_no():
    punch = hikvision_cloud._to_punch(DEVICE, {
        "attendanceStatus": "checkOut", "employeeNo": 42, "time": "2026-09-08T17:00:00+02:00",
    })
    assert punch["device_user_id"] == "42"
    assert punch["punch_type_hint"] == "check_out_work"


def test_to_punch_accepts_the_alternate_timestamp_field():
    punch = hikvision_cloud._to_punch(DEVICE, {
        "attendanceStatus": "breakOut", "employeeNoString": "E-9", "eventTime": "2026-09-08T12:30:00+02:00",
    })
    assert punch["punch_timestamp"] == "2026-09-08T12:30:00+02:00"
    assert punch["punch_type_hint"] == "check_out_break"
    assert punch["raw_status_code"] == 2


def test_to_punch_ignores_a_non_attendance_event():
    """A plain door-open/alarm event carries no attendanceStatus and is not
    a punch — dropping it is correct, not a silent loss."""
    assert hikvision_cloud._to_punch(DEVICE, {"eventType": "doorOpen", "time": "2026-09-08T09:00:00+02:00"}) is None


def test_to_punch_raises_on_an_unrecognised_attendance_status():
    """Documented deliberate behaviour: never guess check-in vs check-out,
    because a wrong guess corrupts payroll silently."""
    with pytest.raises(RuntimeError, match="Unrecognized Hik-Connect attendanceStatus"):
        hikvision_cloud._to_punch(DEVICE, {"attendanceStatus": "teaBreak", "employeeNoString": "E-1", "time": "x"})


def test_to_punch_truncates_an_oversized_status_before_it_reaches_the_log():
    with pytest.raises(RuntimeError) as exc:
        hikvision_cloud._to_punch(DEVICE, {"attendanceStatus": "A" * 5000, "employeeNoString": "E-1", "time": "x"})
    assert len(str(exc.value)) < 200


def test_to_punch_raises_when_an_attendance_event_has_no_timestamp():
    with pytest.raises(RuntimeError, match="no timestamp"):
        hikvision_cloud._to_punch(DEVICE, {"attendanceStatus": "checkIn", "employeeNoString": "E-1"})


def test_to_punch_skips_an_event_with_no_identifiable_user():
    assert hikvision_cloud._to_punch(DEVICE, {"attendanceStatus": "checkIn", "time": "2026-09-08T09:00:00+02:00"}) is None


# ---------------------------------------------------------------------------
# Cloud envelope handling (_unwrap) — finding 40
# ---------------------------------------------------------------------------

def _response(payload, status_code=200):
    return httpx.Response(
        status_code,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://open.hik-connect.com/api/lapp/token/get"),
    )


def test_unwrap_returns_data_on_success():
    assert hikvision_cloud._unwrap(_response({"code": "200", "data": {"accessToken": "t"}}), "token exchange") == {"accessToken": "t"}


def test_unwrap_raises_on_an_application_level_failure_despite_http_200():
    with pytest.raises(RuntimeError, match="code=10002"):
        hikvision_cloud._unwrap(_response({"code": "10002", "msg": "token expired"}), "event list")


def test_unwrap_strips_control_characters_from_platform_text():
    """Untrusted third-party text reaches the worker log and, via sync.py,
    an API response — a newline in it forges log lines."""
    payload = {"code": "500", "msg": "bad\nFORGED LOG LINE\r\tmore"}
    with pytest.raises(RuntimeError) as exc:
        hikvision_cloud._unwrap(_response(payload), "event list")
    message = str(exc.value)
    assert "\n" not in message
    assert "\r" not in message
    assert "\t" not in message


def test_unwrap_truncates_unbounded_platform_text():
    with pytest.raises(RuntimeError) as exc:
        hikvision_cloud._unwrap(_response({"code": "500", "msg": "X" * 10000}), "event list")
    assert str(exc.value).count("X") <= 200


def test_unwrap_rejects_an_oversized_response():
    big = {"code": "200", "data": {"pad": "X" * (hikvision_cloud.MAX_RESPONSE_BYTES + 1024)}}
    with pytest.raises(RuntimeError, match="too large"):
        hikvision_cloud._unwrap(_response(big), "event list")


def test_unwrap_rejects_a_non_object_payload():
    with pytest.raises(RuntimeError, match="expected object"):
        hikvision_cloud._unwrap(_response(["not", "an", "object"]), "token exchange")


def test_cloud_poll_requires_a_serial_number():
    """The cloud API identifies devices by serial, not address."""
    with pytest.raises(RuntimeError, match="no serial_number"):
        hikvision_cloud.poll({"id": 1, "ip_address": "open.hik-connect.com", "port": 443})


def test_cloud_token_exchange_requires_credentials():
    with pytest.raises(RuntimeError, match="missing appKey/appSecret"):
        with httpx.Client() as client:
            hikvision_cloud._get_access_token(client, {"ip_address": "open.hik-connect.com", "port": 443})


# ---------------------------------------------------------------------------
# ISAPI paging caps (finding 35) — against a real HTTP server
# ---------------------------------------------------------------------------

class _IsapiHandler(BaseHTTPRequestHandler):
    """Minimal stand-in for a Hikvision terminal's AcsEvent search endpoint.
    `server.mode` decides whether it behaves, never terminates, or replies
    with an absurdly large body."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep pytest output readable
        pass

    def do_GET(self):
        """`/ISAPI/System/time` — what the clock-drift check reads.
        `server.clock_mode` picks which of the shapes a real terminal can
        answer with."""
        mode = getattr(self.server, "clock_mode", "sync")
        if mode == "missing":
            payload = {"Time": {}}
        else:
            if mode == "naive":
                # Local wall clock with NO offset: unanchored, so drift
                # cannot be computed from it without guessing.
                stamp = datetime.now().replace(microsecond=0).isoformat()
            elif mode == "skewed":
                # The failure this whole feature exists for: a terminal left
                # on factory UTC+8.
                stamp = (datetime.now(timezone.utc) + timedelta(hours=8)).replace(microsecond=0).isoformat()
            else:
                stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            payload = {"Time": {"timeMode": "manual", "localTime": stamp, "timeZone": "CST-8:00:00"}}

        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        mode = self.server.mode

        if mode == "oversized":
            body = json.dumps({"AcsEvent": {"numOfMatches": 1, "InfoList": [], "pad": "X" * (hikvision.MAX_RESPONSE_BYTES + 4096)}}).encode()
        else:
            count = hikvision.PAGE_SIZE if mode == "endless" else 2
            info = [
                {"attendanceStatus": "checkIn" if i % 2 == 0 else "checkOut",
                 "employeeNoString": f"E-{i}",
                 "time": "2026-09-08T09:0%d:00+02:00" % (i % 10)}
                for i in range(count)
            ]
            # A trailing non-attendance event, which a real terminal emits and
            # the adapter must skip rather than choke on.
            info.append({"eventType": "doorOpen", "time": "2026-09-08T09:30:00+02:00"})
            body = json.dumps({"AcsEvent": {"numOfMatches": count, "InfoList": info}}).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _StubServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        # HTTPServer.server_bind() reverse-resolves the bound address with
        # socket.getfqdn(), which stalls ~20s on a LAN address with no PTR
        # record. Nothing under test reads server_name.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


@pytest.fixture(scope="module")
def isapi_server():
    if LAN_ADDRESS is None:
        pytest.skip("no private-LAN address on this host; the adapter guard refuses loopback by design")
    server = _StubServer((LAN_ADDRESS, 0), _IsapiHandler)
    server.mode = "normal"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _device_for(server):
    return {"id": 99, "ip_address": LAN_ADDRESS, "port": server.server_address[1], "auth_username": "", "auth_password": ""}


def test_isapi_poll_reads_and_maps_a_well_behaved_device(isapi_server):
    isapi_server.mode = "normal"
    punches = hikvision.poll(_device_for(isapi_server))

    assert len(punches) == 2, "the non-attendance event should have been skipped, not recorded"
    assert [p["punch_type_hint"] for p in punches] == ["check_in_work", "check_out_work"]
    assert [p["raw_status_code"] for p in punches] == [0, 1]
    assert {p["device_id"] for p in punches} == {99}
    assert [p["device_user_id"] for p in punches] == ["E-0", "E-1"]


def test_isapi_poll_aborts_instead_of_looping_forever(isapi_server):
    """A device that always answers with a full page used to loop without
    bound — ~500 MB of worker RSS in 65s, and because the scheduled sync job
    is max_instances=1, every other device stopped syncing too."""
    isapi_server.mode = "endless"
    with pytest.raises(RuntimeError, match=r"never signalled end of results after \d+ pages"):
        hikvision.poll(_device_for(isapi_server))


def test_isapi_poll_rejects_an_oversized_single_response(isapi_server):
    isapi_server.mode = "oversized"
    with pytest.raises(RuntimeError, match="too large"):
        hikvision.poll(_device_for(isapi_server))


def test_isapi_poll_refuses_a_forbidden_target():
    """The guard runs before any request is made — a device row pointing at
    the cloud-metadata endpoint never gets a connection."""
    with pytest.raises(ValueError):
        hikvision.poll({"id": 1, "ip_address": "169.254.169.254", "port": 80})


def test_paging_caps_are_actually_set():
    for module in (hikvision, hikvision_cloud):
        assert module.MAX_PAGES > 0
        assert module.MAX_PUNCHES == module.MAX_PAGES * module.PAGE_SIZE
        assert module.MAX_RESPONSE_BYTES == 8 * 1024 * 1024


# ---------------------------------------------------------------------------
# Dispatch + error sanitisation (finding 40)
# ---------------------------------------------------------------------------

def test_sync_dispatches_each_device_type_to_its_own_adapter(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "qa-not-a-real-key-0123456789abcdef")
    monkeypatch.setenv("API_BASE_URL", "http://api:8000/api/v1")
    from worker import sync

    assert sync._ADAPTERS["hikvision"] is hikvision.poll
    assert sync._ADAPTERS["hikvision_cloud"] is hikvision_cloud.poll
    assert set(sync._ADAPTERS) == {"zkteco", "hikvision", "hikvision_cloud"}

    with pytest.raises(ValueError, match="Unknown device_type"):
        sync.poll_device({"id": 1, "device_type": "suprema"})


def test_sync_error_text_is_bounded_and_printable(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "qa-not-a-real-key-0123456789abcdef")
    monkeypatch.setenv("API_BASE_URL", "http://api:8000/api/v1")
    from worker import sync

    message = sync._safe_error(RuntimeError("bad\nFORGED\r\x00" + "Y" * 5000))
    assert len(message) <= 300
    assert "\n" not in message
    assert "\r" not in message
    assert "\x00" not in message


# ---------------------------------------------------------------------------
# Device clock drift — every punch is stamped by the device, so a drifted
# clock silently corrupts lateness and overtime. Observed for real on a
# DS-K1T804AMF left on factory UTC+8.
# ---------------------------------------------------------------------------

def test_isapi_device_time_is_read_with_its_offset(isapi_server):
    isapi_server.clock_mode = "sync"
    reading = hikvision.device_time(_device_for(isapi_server))
    assert reading is not None
    assert reading.tzinfo is not None
    assert abs((reading - datetime.now(timezone.utc)).total_seconds()) < 60


def test_isapi_device_time_returns_nothing_when_the_clock_is_unanchored(isapi_server):
    """A local time with no UTC offset cannot be compared to server time
    without guessing a zone, and a guess here would invent drift that may not
    exist (or hide drift that does)."""
    isapi_server.clock_mode = "naive"
    assert hikvision.device_time(_device_for(isapi_server)) is None

    isapi_server.clock_mode = "missing"
    assert hikvision.device_time(_device_for(isapi_server)) is None
    isapi_server.clock_mode = "sync"


def test_clock_skew_measures_a_device_left_on_the_wrong_timezone(isapi_server, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "qa-not-a-real-key-0123456789abcdef")
    monkeypatch.setenv("API_BASE_URL", "http://api:8000/api/v1")
    from worker import sync

    isapi_server.clock_mode = "skewed"
    device = {**_device_for(isapi_server), "device_type": "hikvision"}
    skew = sync.read_clock_skew(device)
    assert skew is not None
    assert abs(skew - 8 * 3600) < 60, "a device 8h ahead must report ~+28800s"

    isapi_server.clock_mode = "sync"
    assert abs(sync.read_clock_skew(device)) < 60


def test_clock_skew_is_never_fatal_and_is_skipped_for_the_cloud_transport(monkeypatch):
    """A device that will not answer a clock query still has punches worth
    collecting, and Hik-Connect exposes no verified clock endpoint at all."""
    monkeypatch.setenv("INTERNAL_API_KEY", "qa-not-a-real-key-0123456789abcdef")
    monkeypatch.setenv("API_BASE_URL", "http://api:8000/api/v1")
    from worker import sync

    assert sync.read_clock_skew({"id": 1, "device_type": "hikvision_cloud"}) is None
    # Unroutable target: the read raises inside the adapter and is swallowed.
    assert sync.read_clock_skew(
        {"id": 2, "device_type": "hikvision", "ip_address": "127.0.0.1", "port": 80}
    ) is None
