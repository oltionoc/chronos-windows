"""Hikvision Hik-Connect (Open Platform) adapter — the same Hikvision
terminal as adapters/hikvision.py, but reached through Hikvision's cloud
instead of directly over the LAN/DDNS address. Added 2026-09-16.

Why both exist: the client's device has cloud + DDNS remote access, and
either transport can carry the same events. Direct (adapters/hikvision.py)
depends only on the device + router + DDNS provider; cloud depends on
Hikvision's platform staying up, but needs no inbound reachability to the
site at all. Both normalize to the identical punch shape, so everything
downstream (ingestion, classification, payroll) is transport-agnostic.

Device record field usage for device_type='hikvision_cloud' (see
backend/app/models.py Device):
  ip_address     -> cloud API host, e.g. "open.hik-connect.com"
  port           -> cloud API port, normally 443
  auth_username  -> Open Platform appKey
  auth_password  -> Open Platform appSecret
  serial_number  -> the device serial the events are pulled for (required)

UNVERIFIED (no Hik-Connect credentials available at implementation time —
this is the one part of the multi-vendor work that could not be exercised
end to end; see BLUEPRINT.md Section 5.5):
  * EVENT_PATH / the event response field names below. The token exchange
    (`/api/lapp/token/get`, `{"code":"200","data":{"accessToken":...}}`) is
    the stable, well-documented part of the lapp API; the access-control
    event search varies by account tier (consumer Hik-Connect vs. the
    signed artemis/HikCentral gateway). Confirm these two constants against
    the client's actual account, then this adapter works unchanged.
  * This module deliberately RAISES on an unrecognized event shape rather
    than silently returning zero punches. A loud per-device error in the
    worker log (and the resulting stale-device alert) is far better than an
    attendance system that quietly records nothing, or worse, guesses
    check-in vs. check-out wrong and corrupts payroll.
"""
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from worker.adapters._target import safe_cloud_host, safe_port
from worker.adapters.hikvision import NON_ATTENDANCE_STATUSES, RAW_CODE, STATUS_MAP

logger = logging.getLogger("worker.adapters.hikvision_cloud")

TOKEN_PATH = "/api/lapp/token/get"
EVENT_PATH = "/api/lapp/device/access/event/list"

LOOKBACK_HOURS = 48
PAGE_SIZE = 50

# SECURITY (SECURITY_REPORT.md Revision 3): same unbounded-paging defect as
# the direct ISAPI adapter — a cloud that keeps answering with a full page
# looped forever, growing memory and starving every other device's sync
# (max_instances=1 on the scheduled job). Also caps the response size and the
# token cache so a hostile or misbehaving platform cannot exhaust the worker.
MAX_PAGES = 400
MAX_PUNCHES = MAX_PAGES * PAGE_SIZE
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_CACHED_TOKENS = 64
# A platform-supplied expireTime is untrusted input: an absurd value would
# pin a stale token in the cache indefinitely.
MAX_TOKEN_TTL_SECONDS = 7 * 24 * 3600

# Access tokens are long-lived (days), so refetching one per 5-minute poll
# would be pointless traffic and risks the platform's rate limits. Cached
# per (host, appKey) in-process; worker is a single long-lived process, and
# a duplicate fetch from two concurrent polls is harmless, so no lock.
_token_cache: dict[tuple[str, str], tuple[str, float]] = {}
_TOKEN_EXPIRY_MARGIN_SECONDS = 300


def _base_url(device: dict) -> str:
    """SECURITY: always HTTPS, and only ever to a Hikvision Open Platform
    host. The scheme used to be derived from the port (80 -> http), so a
    one-integer edit to the device row silently put the appKey/appSecret on
    the wire in cleartext; and the host was whatever the row said, so
    repointing the row turned the stored credentials into an exfiltration
    primitive (see backend/app/routers/devices.py's matching fix)."""
    host = safe_cloud_host(device["ip_address"])
    port = safe_port(device["port"])
    return f"https://{host}:{port}"


def _unwrap(resp: httpx.Response, what: str) -> dict:
    """Hik-Connect wraps everything in {"code": "200", "msg": ..., "data": ...}
    and returns HTTP 200 even for application-level failures, so the envelope
    has to be checked explicitly."""
    resp.raise_for_status()
    if len(resp.content) > MAX_RESPONSE_BYTES:
        raise RuntimeError(
            f"Hik-Connect {what} response too large ({len(resp.content)} bytes)"
        )
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Hik-Connect {what} returned {type(payload).__name__}, expected object")
    code = str(payload.get("code"))
    if code != "200":
        # The platform's `msg` is untrusted third-party text that ends up in
        # worker logs and, via sync.py, in an API response — truncate it and
        # strip control characters so it cannot forge log lines.
        msg = "".join(c for c in str(payload.get("msg", ""))[:200] if c.isprintable())
        raise RuntimeError(f"Hik-Connect {what} failed: code={code} msg={msg!r}")
    data = payload.get("data") or {}
    if not isinstance(data, (dict, list)):
        raise RuntimeError(f"Hik-Connect {what} data was {type(data).__name__}, expected object/array")
    return data


def _get_access_token(client: httpx.Client, device: dict) -> str:
    host = safe_cloud_host(device["ip_address"])
    app_key = device.get("auth_username") or ""
    app_secret = device.get("auth_password") or ""
    if not app_key or not app_secret:
        raise RuntimeError("Hik-Connect device is missing appKey/appSecret credentials")

    cache_key = (host, app_key)
    cached = _token_cache.get(cache_key)
    if cached is not None and cached[1] > time.time() + _TOKEN_EXPIRY_MARGIN_SECONDS:
        return cached[0]

    data = _unwrap(
        client.post(
            f"{_base_url(device)}{TOKEN_PATH}",
            data={"appKey": app_key, "appSecret": app_secret},
        ),
        "token exchange",
    )
    token = data.get("accessToken")
    if not token:
        raise RuntimeError("Hik-Connect token response contained no accessToken")

    # expireTime is epoch milliseconds; fall back to a conservative hour if
    # the platform omits it.
    if not isinstance(token, str):
        raise RuntimeError("Hik-Connect accessToken was not a string")

    # expireTime is epoch milliseconds; fall back to a conservative hour if
    # the platform omits it, and never trust it past MAX_TOKEN_TTL_SECONDS.
    expire_ms = data.get("expireTime")
    try:
        expires_at = float(expire_ms) / 1000.0 if expire_ms else time.time() + 3600
    except (TypeError, ValueError):
        expires_at = time.time() + 3600
    expires_at = min(expires_at, time.time() + MAX_TOKEN_TTL_SECONDS)

    if len(_token_cache) >= MAX_CACHED_TOKENS and cache_key not in _token_cache:
        _token_cache.clear()
    _token_cache[cache_key] = (token, expires_at)
    return token


def _to_punch(device: dict, item: dict) -> dict | None:
    status = item.get("attendanceStatus")
    punch_type_hint = STATUS_MAP.get(status)
    if punch_type_hint is None:
        if status is not None and status not in NON_ATTENDANCE_STATUSES:
            # A real attendance event whose status we don't know how to map —
            # skipping would silently lose a punch, so surface it instead.
            # Truncated: this is untrusted platform input that reaches the logs.
            raise RuntimeError(f"Unrecognized Hik-Connect attendanceStatus: {str(status)[:80]!r}")
        # No attendance semantics at all (plain door-open/alarm event).
        return None

    device_user_id = item.get("employeeNoString") or str(item.get("employeeNo") or "")
    if not device_user_id:
        return None

    punch_timestamp = item.get("time") or item.get("eventTime")
    if not punch_timestamp:
        raise RuntimeError("Hik-Connect event carried no timestamp field ('time'/'eventTime')")

    return {
        "device_id": device["id"],
        "device_user_id": device_user_id,
        "punch_timestamp": punch_timestamp,
        "raw_status_code": RAW_CODE[punch_type_hint],
        "punch_type_hint": punch_type_hint,
    }


def poll(device: dict) -> list[dict]:
    serial = device.get("serial_number")
    if not serial:
        raise RuntimeError(
            "Hik-Connect device has no serial_number — the cloud API identifies "
            "devices by serial, not by address"
        )

    # Trimmed to whole seconds: the device declares startTime/endTime as max
    # 25 chars (AcsEvent/capabilities) and Python's isoformat() emits 32 with
    # microseconds. Over-length made the device answer "NO MATCH" instead of
    # erroring — a silent zero-punch sync, observed on DS-K1T804AMF V1.4.0.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(hours=LOOKBACK_HOURS)

    punches: list[dict] = []
    with httpx.Client(timeout=20) as client:
        token = _get_access_token(client, device)

        for page in range(MAX_PAGES):
            data = _unwrap(
                client.post(
                    f"{_base_url(device)}{EVENT_PATH}",
                    data={
                        "accessToken": token,
                        "deviceSerial": serial,
                        "startTime": start.isoformat(),
                        "endTime": now.isoformat(),
                        "pageStart": page,
                        "pageSize": PAGE_SIZE,
                    },
                ),
                "event list",
            )

            items = data if isinstance(data, list) else data.get("list") or data.get("events") or []
            if not isinstance(items, list):
                raise RuntimeError(
                    f"Unexpected Hik-Connect event payload shape: {type(items).__name__}"
                )

            for item in items:
                if not isinstance(item, dict):
                    raise RuntimeError(
                        f"Unexpected Hik-Connect event entry shape: {type(item).__name__}"
                    )
                punch = _to_punch(device, item)
                if punch is not None:
                    punches.append(punch)

            if len(punches) > MAX_PUNCHES:
                raise RuntimeError(
                    f"Hik-Connect returned more than {MAX_PUNCHES} punches in one poll — aborting"
                )

            if len(items) < PAGE_SIZE:
                break
        else:
            raise RuntimeError(
                f"Hik-Connect never signalled end of results after {MAX_PAGES} pages — aborting"
            )

    return punches
