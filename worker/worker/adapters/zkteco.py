"""ZKTeco K40 adapter — pyzk over TCP 4370. Extracted unchanged from the
original single-vendor worker/worker/sync.py (2026-09-16 multi-vendor split)
— behavior is identical to before, just moved.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from worker.adapters._target import safe_host, safe_port
from worker.config import settings


def device_time(device: dict) -> datetime | None:
    """The terminal's own clock, as an absolute instant.

    The K40 reports a naive local time, exactly like the punches it stores,
    so it is anchored with the same DEVICE_TIMEZONE setting `poll` uses. That
    is the point: if the device clock drifts, every punch drifts with it, and
    this reading is what makes that visible."""
    from zk import ZK

    zk = ZK(safe_host(device["ip_address"]), port=safe_port(device["port"]), timeout=10, ommit_ping=True)
    conn = None
    try:
        conn = zk.connect()
        raw = conn.get_time()
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                pass
    if raw is None:
        return None
    if raw.tzinfo is not None:
        return raw
    return raw.replace(tzinfo=ZoneInfo(settings.device_timezone))


def poll(device: dict) -> list[dict]:
    """Connects to one K40 device via pyzk and returns raw punches formatted
    for `api`'s `/internal/ingest/punches` body. Every poll re-reads the
    full on-device log (K40 retains punches until explicitly cleared, and
    Phase 1 does not clear device logs to avoid data-loss risk); dedup is
    enforced server-side by `api`'s ingestion endpoint, so re-syncing the
    same log is a cheap no-op here."""
    from zk import ZK

    tz = ZoneInfo(settings.device_timezone)
    # SECURITY (SECURITY_REPORT.md Revision 3): `ip_address` became free text
    # in migration 0009, so apply the same outbound-target guard the HTTP
    # adapters use — a raw TCP connect to loopback/link-local is no more
    # legitimate here than an HTTP one.
    zk = ZK(safe_host(device["ip_address"]), port=safe_port(device["port"]), timeout=10, ommit_ping=True)
    conn = None
    try:
        conn = zk.connect()
        records = conn.get_attendance() or []
    finally:
        if conn is not None:
            try:
                conn.disconnect()
            except Exception:
                pass

    punches = []
    for r in records:
        local_dt = r.timestamp.replace(tzinfo=tz)
        utc_dt = local_dt.astimezone(timezone.utc)
        raw_status_code = getattr(r, "punch", None)
        if raw_status_code is None:
            raw_status_code = getattr(r, "status", 0)
        punches.append(
            {
                "device_id": device["id"],
                "device_user_id": str(r.user_id),
                "punch_timestamp": utc_dt.isoformat(),
                "raw_status_code": int(raw_status_code),
            }
        )
    return punches
