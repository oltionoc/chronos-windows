"""HTTP client for worker -> api communication (BLUEPRINT.md Section 2.2).
Never touches PostgreSQL directly — all state changes go through `api`'s
internal ingestion endpoints, authenticated with the shared X-Internal-Key
header.
"""
from datetime import date

import httpx

from worker.config import settings

_headers = {"X-Internal-Key": settings.internal_api_key}


def get_active_devices() -> list[dict]:
    resp = httpx.get(f"{settings.api_base_url}/internal/devices", headers=_headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def ingest_punches(punches: list[dict]) -> dict:
    resp = httpx.post(
        f"{settings.api_base_url}/internal/ingest/punches",
        headers=_headers,
        json={"punches": punches},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def process_daily_status(work_date: date) -> dict:
    resp = httpx.post(
        f"{settings.api_base_url}/internal/process/daily-status",
        headers=_headers,
        json={"work_date": work_date.isoformat()},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()


def send_heartbeat(device_id: int, clock_skew_seconds: int | None = None) -> None:
    httpx.patch(
        f"{settings.api_base_url}/internal/devices/{device_id}/heartbeat",
        headers=_headers,
        json={"clock_skew_seconds": clock_skew_seconds},
        timeout=15,
    )
