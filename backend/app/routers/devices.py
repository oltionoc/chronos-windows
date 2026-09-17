from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import false
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import assert_location_access, get_current_user, require_manager_or_admin
from app.models import Device, Location, User
from app.schemas import DeviceCreate, DeviceOut, DeviceTestConnectionResult, DeviceUpdate
from app.services.device_net import assert_cloud_host, assert_safe_target

router = APIRouter(prefix="/devices", tags=["devices"], dependencies=[Depends(require_manager_or_admin)])

# SECURITY (SECURITY_REPORT.md Revision 3 — "device credential exfiltration
# via retargeting"): `auth_password` is deliberately never returned by
# DeviceOut, but `test_connection` sends it to whatever host the row points
# at. Changing any of these fields without re-supplying the secret would
# therefore let someone who cannot *read* the stored credential still have it
# delivered to a host of their choosing. Requiring it in the same request
# means the secret is overwritten rather than harvested.
_RETARGETING_FIELDS = ("ip_address", "port", "device_type")

# Kept in step with routers/reports.py's alert threshold, so Test Connection
# and the Alerts page never disagree about whether a clock is acceptable.
CLOCK_DRIFT_TOLERANCE_SECONDS = 120


def _assert_target_allowed(device: Device) -> None:
    """Validates the stored outbound target right before `api` connects to it
    — rows written before the Revision 3 schema validation existed are not
    re-validated on read, so this is the enforcement point that covers them."""
    if device.device_type == "hikvision_cloud":
        assert_cloud_host(device.ip_address)
    assert_safe_target(device.ip_address)


def _connection_error_detail(exc: Exception) -> str:
    """Never echo the raw exception: httpx puts the full request URL in its
    message, which reflects an operator-supplied host (and any injected path)
    straight back into the API response and turns this endpoint into a much
    more precise internal-network probe. Report the failure class and, for an
    HTTP-level rejection, the status code — enough to tell "wrong password"
    from "not reachable" without echoing attacker-controlled text."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"Device rejected the request: HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "Timed out connecting to the device"
    if isinstance(exc, httpx.TransportError):
        return "Could not connect to the device"
    if isinstance(exc, ValueError):
        return str(exc)
    return f"Connection failed ({type(exc).__name__})"


def _serialize(device: Device) -> DeviceOut:
    out = DeviceOut.model_validate(device)
    out.location_name = device.location.name if device.location else None
    return out


def _get_device_or_404(db: Session, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.get("", response_model=list[DeviceOut])
def list_devices(
    location_id: int | None = None,
    is_active: bool | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(Device)
    if user.role == "manager":
        if user.location_id is None:
            q = q.filter(false())
        else:
            q = q.filter(Device.location_id == user.location_id)
    if location_id is not None:
        q = q.filter(Device.location_id == location_id)
    if is_active is not None:
        q = q.filter(Device.is_active == is_active)
    if search:
        like = f"%{search}%"
        q = q.filter((Device.label.ilike(like)) | (Device.serial_number.ilike(like)))
    return [_serialize(d) for d in q.order_by(Device.label).all()]


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    assert_location_access(user, payload.location_id)
    if db.get(Location, payload.location_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not found")
    if payload.device_type == "hikvision_cloud":
        try:
            assert_cloud_host(payload.ip_address)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    device = Device(**payload.model_dump())
    db.add(device)
    db.commit()
    db.refresh(device)
    return _serialize(device)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    device = _get_device_or_404(db, device_id)
    assert_location_access(user, device.location_id)
    return _serialize(device)


@router.put("/{device_id}", response_model=DeviceOut)
def update_device(device_id: int, payload: DeviceUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    device = _get_device_or_404(db, device_id)
    assert_location_access(user, device.location_id)
    data = payload.model_dump(exclude_unset=True)
    if "location_id" in data:
        assert_location_access(user, data["location_id"])

    retargeted = any(f in data and data[f] != getattr(device, f) for f in _RETARGETING_FIELDS)
    if retargeted and device.auth_password and "auth_password" not in data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Changing a device's address, port or type also requires re-entering "
                "its password, because the stored one is sent to the new target."
            ),
        )

    for k, v in data.items():
        setattr(device, k, v)
    if device.device_type == "hikvision_cloud":
        try:
            assert_cloud_host(device.ip_address)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    db.refresh(device)
    return _serialize(device)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    device = _get_device_or_404(db, device_id)
    assert_location_access(user, device.location_id)
    db.delete(device)
    db.commit()


def _read_isapi_clock_skew(device: Device, auth: httpx.DigestAuth) -> int | None:
    """Seconds the device clock is ahead of ours, or None if unreadable.

    Mirrors worker/worker/adapters/hikvision.py::device_time, including its
    refusal to guess: a local time with no UTC offset is unanchored, and
    inventing a zone would either invent drift or hide it."""
    try:
        resp = httpx.get(
            f"http://{device.ip_address}:{device.port}/ISAPI/System/time?format=json",
            auth=auth,
            timeout=5,
        )
        resp.raise_for_status()
        local_time = ((resp.json() or {}).get("Time") or {}).get("localTime")
        if not isinstance(local_time, str):
            return None
        parsed = datetime.fromisoformat(local_time)
        if parsed.tzinfo is None:
            return None
        return int(round((parsed - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        # Reachability is the question this endpoint answers; a clock it
        # could not read must never turn a working device into a failure.
        return None


def _zk_clock_skew(device: Device, conn) -> int | None:
    """Same for a ZKTeco unit, whose clock (like its punches) is naive local
    time. It is anchored with the device's own location timezone — `worker`
    uses its DEVICE_TIMEZONE env var for this, which `api` does not have, and
    the location record is the same value in every deployment where the two
    agree."""
    try:
        raw = conn.get_time()
        if raw is None:
            return None
        if raw.tzinfo is None:
            tz = (device.location.timezone if device.location else None) or "Europe/Tirane"
            raw = raw.replace(tzinfo=ZoneInfo(tz))
        return int(round((raw - datetime.now(timezone.utc)).total_seconds()))
    except Exception:
        return None


def _store_clock_skew(db: Session, device: Device, skew: int | None) -> None:
    if skew is None:
        return
    device.clock_skew_seconds = skew
    device.clock_checked_at = datetime.now(timezone.utc)
    db.commit()


def _reachable_detail(skew: int | None) -> str:
    """Test Connection is where someone is standing in front of the device,
    so it is the right moment to tell them the clock is wrong — that is the
    error that silently corrupts every punch it stamps."""
    if skew is None:
        return "Connected successfully"
    if abs(skew) <= CLOCK_DRIFT_TOLERANCE_SECONDS:
        return "Connected successfully. Device clock matches the server."
    minutes = abs(round(skew / 60))
    direction = "ahead of" if skew > 0 else "behind"
    return (
        f"Connected, but the device clock is {minutes} minute(s) {direction} the server. "
        "Punch times will be wrong by that much until it is corrected."
    )


@router.post("/{device_id}/test-connection", response_model=DeviceTestConnectionResult)
def test_connection(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """One-off synchronous reachability check, run from `api` directly (not
    through `worker`) per BLUEPRINT.md Section 4.3 — setup verification
    only, not the recurring sync path. Dispatches by device_type since each
    vendor speaks a different protocol; see worker/worker/sync.py for the
    equivalent per-vendor dispatch on the actual polling path."""
    device = _get_device_or_404(db, device_id)
    assert_location_access(user, device.location_id)

    try:
        _assert_target_allowed(device)
    except ValueError as exc:
        return DeviceTestConnectionResult(reachable=False, detail=str(exc))

    if device.device_type == "hikvision_cloud":
        # Reachability for the cloud transport means "the Open Platform
        # accepts these credentials" — the device itself is behind
        # Hikvision's cloud and isn't directly pingable from here. Mirrors
        # worker/worker/adapters/hikvision_cloud.py's token exchange.
        # SECURITY: always HTTPS. The scheme used to be chosen from the port
        # (80 -> http), which meant one edit to an integer silently put the
        # Open Platform appKey/appSecret on the wire in cleartext.
        try:
            resp = httpx.post(
                f"https://{device.ip_address}:{device.port}/api/lapp/token/get",
                data={"appKey": device.auth_username or "", "appSecret": device.auth_password or ""},
                timeout=10,
            )
            resp.raise_for_status()
            payload = resp.json()
            if str(payload.get("code")) != "200":
                return DeviceTestConnectionResult(
                    reachable=False, detail="Hik-Connect rejected the credentials"
                )
            return DeviceTestConnectionResult(reachable=True, detail="Cloud credentials accepted")
        except Exception as exc:  # network, TLS, or malformed-response errors
            return DeviceTestConnectionResult(reachable=False, detail=_connection_error_detail(exc))

    if device.device_type == "hikvision":
        try:
            auth = httpx.DigestAuth(device.auth_username or "", device.auth_password or "")
            resp = httpx.get(
                f"http://{device.ip_address}:{device.port}/ISAPI/System/deviceInfo",
                auth=auth,
                timeout=5,
            )
            resp.raise_for_status()
            skew = _read_isapi_clock_skew(device, auth)
            _store_clock_skew(db, device, skew)
            return DeviceTestConnectionResult(reachable=True, detail=_reachable_detail(skew))
        except Exception as exc:  # httpx raises a variety of connection/auth errors
            return DeviceTestConnectionResult(reachable=False, detail=_connection_error_detail(exc))

    try:
        from zk import ZK  # imported lazily — only needed for this endpoint

        zk = ZK(str(device.ip_address), port=device.port, timeout=5)
        conn = zk.connect()
        try:
            skew = _zk_clock_skew(device, conn)
        finally:
            conn.disconnect()
        _store_clock_skew(db, device, skew)
        return DeviceTestConnectionResult(reachable=True, detail=_reachable_detail(skew))
    except Exception as exc:  # pyzk raises a variety of socket/protocol errors
        return DeviceTestConnectionResult(reachable=False, detail=_connection_error_detail(exc))


@router.post("/{device_id}/sync", status_code=status.HTTP_202_ACCEPTED)
def trigger_sync(device_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Manual on-demand sync trigger — proxies to `worker`'s internal
    `/sync/{device_id}` endpoint (see worker/worker/main.py), per
    BLUEPRINT.md Section 4.3. `worker` performs the actual pyzk poll and
    pushes results back to `api`'s ingestion endpoint, same as its scheduled
    interval sync — this just triggers it on demand instead of waiting for
    the next interval.
    """
    device = _get_device_or_404(db, device_id)
    assert_location_access(user, device.location_id)

    try:
        resp = httpx.post(
            f"{settings.worker_internal_url}/sync/{device_id}",
            headers={"X-Internal-Key": settings.internal_api_key},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Could not reach sync worker: {exc}"
        )
