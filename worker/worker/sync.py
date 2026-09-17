"""Device polling — BLUEPRINT.md Section 5.1. Dispatches to the matching
vendor adapter (worker/worker/adapters/) per device's device_type — added
2026-09-16 for multi-vendor support (originally ZKTeco-only)."""
import logging
from datetime import datetime, timezone

from worker import api_client
from worker.adapters import hikvision, hikvision_cloud, zkteco

logger = logging.getLogger("worker.sync")

_ADAPTERS = {
    "zkteco": zkteco.poll,
    "hikvision": hikvision.poll,
    "hikvision_cloud": hikvision_cloud.poll,
}

# Vendors whose clock can be read back. Hik-Connect exposes no verified
# device-clock endpoint, so cloud-transport devices simply report no reading
# rather than a guessed one.
_CLOCK_READERS = {
    "zkteco": zkteco.device_time,
    "hikvision": hikvision.device_time,
}


def read_clock_skew(device: dict) -> int | None:
    """Seconds the device's clock is AHEAD of ours (negative = behind).

    Never raises: a device that will not answer a clock query still has
    punches worth collecting, so a failure here is logged and reported as "no
    reading", not as a failed sync."""
    reader = _CLOCK_READERS.get(device["device_type"])
    if reader is None:
        return None
    try:
        device_now = reader(device)
    except Exception as exc:
        logger.warning("Could not read clock of device %s: %s", device["id"], _safe_error(exc))
        return None
    if device_now is None:
        return None
    return int(round((device_now - datetime.now(timezone.utc)).total_seconds()))


def poll_device(device: dict) -> list[dict]:
    adapter = _ADAPTERS.get(device["device_type"])
    if adapter is None:
        raise ValueError(f"Unknown device_type: {device['device_type']!r}")
    return adapter(device)


def _safe_error(exc: Exception) -> str:
    """Poll failures surface to an operator through `api`'s
    POST /devices/{id}/sync response and the worker log, but the text can
    contain untrusted device/cloud output. Bound it and drop control
    characters so a device cannot forge log lines or flood the response
    (SECURITY_REPORT.md Revision 3)."""
    return "".join(c for c in str(exc)[:300] if c.isprintable())


def sync_one_device(device: dict) -> dict:
    try:
        punches = poll_device(device)
    except Exception as exc:
        message = _safe_error(exc)
        label = "".join(c for c in str(device.get("label", ""))[:80] if c.isprintable())
        logger.error("Failed to poll device %s (%s): %s", device["id"], label, message)
        return {"device_id": device["id"], "error": message}

    result = {"device_id": device["id"], "punches_read": len(punches)}
    if punches:
        ingest_result = api_client.ingest_punches(punches)
        result.update(ingest_result)

    clock_skew_seconds = read_clock_skew(device)
    result["clock_skew_seconds"] = clock_skew_seconds
    api_client.send_heartbeat(device["id"], clock_skew_seconds)
    return result


def sync_all_devices() -> list[dict]:
    devices = api_client.get_active_devices()
    results = []
    for device in devices:
        results.append(sync_one_device(device))
    return results
