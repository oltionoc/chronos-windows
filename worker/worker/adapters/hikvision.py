"""Hikvision ISAPI adapter — HTTP + digest auth, for the DS-K1T804BEF (and
other Hikvision access-control/face-recognition terminals speaking the same
ISAPI AcsEvent search API). Added 2026-09-16 for multi-vendor support.

Unlike ZKTeco, Hikvision terminals in "attendance mode" already classify
each event (`attendanceStatus`: checkIn/checkOut/breakIn/breakOut/...) — we
pass that straight through as `punch_type_hint` so `api`'s
services/classify.py trusts it directly instead of inferring from
alternating parity + break-window overlap. Timestamps also arrive with
their own UTC offset already attached, so — unlike ZKTeco's naive
device-local timestamps — no DEVICE_TIMEZONE guess is needed here.

ASSUMPTION (no real hardware available to verify against): reachability is
over plain HTTP (ISAPI's default), and the search window is a fixed
lookback rather than an incremental cursor — worker holds no state between
polls (BLUEPRINT.md Section 2.2: "worker never touches PostgreSQL
directly"), and re-fetching the same window every cycle is a cheap no-op
since `api`'s ingestion endpoint dedups server-side (same reasoning as the
ZKTeco adapter's "re-read the whole log" behavior). 48h comfortably covers
the default 5-minute poll interval with margin for a weekend/holiday of
worker downtime, without querying unbounded history every cycle.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from worker.adapters._target import safe_host, safe_port

logger = logging.getLogger("worker.adapters.hikvision")

LOOKBACK_HOURS = 48
PAGE_SIZE = 10  # device-declared max (AcsEvent/capabilities: maxResults @max=10)

# SECURITY (SECURITY_REPORT.md Revision 3): the paging loop used to end only
# when the device said so. A device that keeps answering "here are PAGE_SIZE
# more" — a hostile one, or simply a firmware that mis-reports numOfMatches —
# kept the loop running forever, growing `punches` without bound and, because
# the scheduled sync job runs with max_instances=1, permanently starving every
# other device's sync. Measured: ~500 MB of worker RSS in 65s. These two caps
# bound both the memory and the time any single device can consume.
MAX_PAGES = 400
MAX_PUNCHES = MAX_PAGES * PAGE_SIZE
# 48h of one terminal's events is kilobytes; anything near this is a device
# trying to exhaust worker memory in a single response.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# Statuses the device legitimately reports that carry no attendance meaning.
# "undefined" is a real value in this firmware's own declared enum
# (AcsEvent/capabilities: attendanceStatus @opt
# "undefined,checkIn,checkOut,breakOut,breakIn,overtimeIn,overtimeOut") and
# means "this event is not a check-in/out" — it must be skipped, never
# treated as an unmappable surprise.
NON_ATTENDANCE_STATUSES = {"undefined"}

# Hikvision's attendanceStatus values -> chronos's punch_type_hint enum.
# overtimeIn/overtimeOut used to fold into the plain work pair, which threw
# away the device's own statement that a stretch was overtime; since
# migration 0014 they are kept distinct, and services/recompute.py exempts
# explicitly badged overtime from the daily overtime threshold. Public
# because the hikvision_cloud adapter reuses the same event semantics over a
# different transport.
STATUS_MAP = {
    "checkIn": "check_in_work",
    "checkOut": "check_out_work",
    "breakIn": "check_in_break",
    "breakOut": "check_out_break",
    "overtimeIn": "check_in_overtime",
    "overtimeOut": "check_out_overtime",
}

# raw_status_code has no protocol meaning here (Hikvision events are already
# classified via attendanceStatus/punch_type_hint) — this is just a stable,
# human-legible encoding so the dedup unique key still makes sense.
# Values match ZKTeco's own punch codes so services/classify.py reads both
# vendors with one rule (2/3 break, 4/5 overtime).
RAW_CODE = {
    "check_in_work": 0,
    "check_out_work": 1,
    "check_in_break": 3,
    "check_out_break": 2,
    "check_in_overtime": 4,
    "check_out_overtime": 5,
}


def _read_json(resp: httpx.Response) -> dict:
    resp.raise_for_status()
    if len(resp.content) > MAX_RESPONSE_BYTES:
        raise RuntimeError(
            f"Device response too large ({len(resp.content)} bytes, max {MAX_RESPONSE_BYTES})"
        )
    payload = resp.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected ISAPI payload shape: {type(payload).__name__}")
    return payload


def device_time(device: dict) -> datetime | None:
    """The terminal's own clock, as an absolute instant.

    Every punch is stamped by the device, so a device whose clock has drifted
    produces lateness and overtime figures that are wrong by exactly that
    drift, with nothing in the data to show it. Observed for real on a
    DS-K1T804AMF still on its factory UTC+8: events arrived stamped
    `+08:00` and turned an on-time arrival into 61 minutes late.

    Returns None when the device reports a local time with no UTC offset —
    the reading is then unanchored and comparing it to server time would
    invent drift that may not exist.
    """
    host = safe_host(device["ip_address"])
    port = safe_port(device["port"])
    auth = httpx.DigestAuth(device.get("auth_username") or "", device.get("auth_password") or "")
    with httpx.Client(auth=auth, timeout=10) as client:
        payload = _read_json(client.get(f"http://{host}:{port}/ISAPI/System/time?format=json"))
    local_time = (payload.get("Time") or {}).get("localTime")
    if not isinstance(local_time, str):
        return None
    try:
        parsed = datetime.fromisoformat(local_time)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def list_users(device: dict) -> list[dict]:
    """Read the users enrolled on a Hikvision terminal, via ISAPI
    UserInfo/Search. Read-only. Pages in blocks of 30 (the endpoint's own max)
    up to MAX_PAGES, the same bound the punch poll uses, so one device can
    never spin this forever.

    Returns {device_user_id, name} per user. `employeeNo` is the number staff
    key/scan under; `name` is the enrolled display name."""
    host = safe_host(device["ip_address"])
    port = safe_port(device["port"])
    auth = httpx.DigestAuth(device.get("auth_username") or "", device.get("auth_password") or "")
    url = f"http://{host}:{port}/ISAPI/AccessControl/UserInfo/Search?format=json"
    search_id = uuid.uuid4().hex[:16]

    users: list[dict] = []
    position = 0
    page_size = 30
    with httpx.Client(auth=auth, timeout=15) as client:
        for _ in range(MAX_PAGES):
            body = {
                "UserInfoSearchCond": {
                    "searchID": search_id,
                    "searchResultPosition": position,
                    "maxResults": page_size,
                }
            }
            data = _read_json(client.post(url, json=body)).get("UserInfoSearch") or {}
            if not isinstance(data, dict):
                raise RuntimeError(f"Unexpected UserInfoSearch shape: {type(data).__name__}")
            info_list = data.get("UserInfo") or []
            if not isinstance(info_list, list):
                raise RuntimeError(f"Unexpected UserInfo shape: {type(info_list).__name__}")

            for item in info_list:
                if not isinstance(item, dict):
                    continue
                uid = str(item.get("employeeNo", "") or "").strip()
                if not uid:
                    continue
                users.append({"device_user_id": uid, "name": str(item.get("name", "") or "").strip()})

            num = data.get("numOfMatches", 0)
            if not isinstance(num, int) or num <= 0:
                break
            position += num
            if num < page_size or data.get("responseStatusStrg") == "NO MATCH":
                break
            if len(users) > MAX_PUNCHES:
                raise RuntimeError(f"Device returned more than {MAX_PUNCHES} users — aborting")
        else:
            raise RuntimeError(f"Device never signalled end of user list after {MAX_PAGES} pages")

    return users


def poll(device: dict) -> list[dict]:
    host = safe_host(device["ip_address"])
    port = safe_port(device["port"])
    auth = httpx.DigestAuth(device.get("auth_username") or "", device.get("auth_password") or "")
    base_url = f"http://{host}:{port}/ISAPI/AccessControl/AcsEvent"

    # Trimmed to whole seconds: the device declares startTime/endTime as max
    # 25 chars (AcsEvent/capabilities) and Python's isoformat() emits 32 with
    # microseconds. Over-length made the device answer "NO MATCH" instead of
    # erroring — a silent zero-punch sync, observed on DS-K1T804AMF V1.4.0.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    start = now - timedelta(hours=LOOKBACK_HOURS)
    # searchID is length-constrained (capabilities: @min 1, @max 20) — a full
    # uuid4 string is 36 chars and the device rejects it.
    search_id = uuid.uuid4().hex[:16]

    punches: list[dict] = []
    position = 0
    with httpx.Client(auth=auth, timeout=15) as client:
        for page in range(MAX_PAGES):
            body = {
                "AcsEventCond": {
                    "searchID": search_id,
                    "searchResultPosition": position,
                    "maxResults": PAGE_SIZE,
                    "major": 0,
                    "minor": 0,
                    "eventAttribute": "attendance",
                    "startTime": start.isoformat(),
                    "endTime": now.isoformat(),
                }
            }
            data = _read_json(client.post(f"{base_url}?format=json", json=body)).get("AcsEvent") or {}
            if not isinstance(data, dict):
                raise RuntimeError(f"Unexpected AcsEvent shape: {type(data).__name__}")

            info_list = data.get("InfoList") or []
            if not isinstance(info_list, list):
                raise RuntimeError(f"Unexpected InfoList shape: {type(info_list).__name__}")

            for item in info_list:
                if not isinstance(item, dict):
                    raise RuntimeError(f"Unexpected AcsEvent entry shape: {type(item).__name__}")
                # The query already asks the device for attendance events only
                # (eventAttribute=attendance), so every entry here is a punch
                # and must be recorded. Whether the device *labels* it is a
                # separate question: a terminal with attendance mode off
                # reports attendanceStatus="undefined" for a perfectly real
                # badge (observed on DS-K1T804AMF V1.4.0). Dropping those
                # would silently ingest nothing at all, so an unlabelled punch
                # is stored with no hint and classified by
                # services/classify.py's sequence/break-window inference —
                # the same path the ZKTeco adapter has always relied on.
                status = item.get("attendanceStatus")
                punch_type_hint = STATUS_MAP.get(status)
                device_user_id = item.get("employeeNoString") or str(item.get("employeeNo", ""))
                if not device_user_id:
                    continue
                punch_timestamp = item.get("time")
                if not punch_timestamp:
                    raise RuntimeError("ISAPI event carried no 'time' field")
                punches.append(
                    {
                        "device_id": device["id"],
                        "device_user_id": device_user_id,
                        "punch_timestamp": punch_timestamp,
                        # 0 when the device didn't classify: deliberately not
                        # the event's own `minor`, because classify.py reads
                        # raw_status_code 2/3 as ZKTeco break markers and a
                        # colliding minor would be misread as a break punch.
                        "raw_status_code": RAW_CODE[punch_type_hint] if punch_type_hint else 0,
                        "punch_type_hint": punch_type_hint,
                    }
                )

            if len(punches) > MAX_PUNCHES:
                raise RuntimeError(
                    f"Device returned more than {MAX_PUNCHES} punches in one poll — aborting"
                )

            num_matches = data.get("numOfMatches", 0)
            if not isinstance(num_matches, int) or num_matches <= 0:
                break
            position += num_matches
            if num_matches < PAGE_SIZE or data.get("responseStatusStrg") == "NO MATCH":
                break
        else:
            raise RuntimeError(
                f"Device never signalled end of results after {MAX_PAGES} pages — aborting"
            )

    return punches
