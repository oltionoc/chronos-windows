import hmac

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.security import COOKIE_NAME, decode_access_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")

    user = db.get(User, payload.get("user_id"))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_any_role(user: User = Depends(get_current_user)) -> User:
    # Both admin and manager are valid authenticated roles for endpoints
    # that apply row-level (manager) scoping instead of a role gate.
    return user


def require_manager_or_admin(user: User = Depends(get_current_user)) -> User:
    # 2026-08-24: managers get full write access (employees, shift
    # schedules, devices, payroll, config) for their own location — enforced
    # per-endpoint via assert_location_access below, not by this role gate
    # alone. Originally payroll/config had a separate per-manager opt-in
    # gate (require_payroll_access + users.can_manage_payroll); removed
    # 2026-08-25 per client direction — managers get total access to their
    # own location, no per-manager flag needed.
    if user.role not in ("admin", "manager"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or Manager access required")
    return user


def assert_location_access(user: User, location_id: int | None) -> None:
    """Write-endpoint guard: admin can touch any location; a manager (with
    require_manager_or_admin already passed) can only touch their own
    assigned location. Call after validating the target location_id
    exists."""
    if user.role == "admin":
        return
    if location_id is None or user.location_id is None or user.location_id != location_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your location")


def verify_internal_key(x_internal_key: str = Header(default="")) -> None:
    # hmac.compare_digest avoids leaking the key's correct prefix length via
    # a response-time side channel (a plain `!=` string compare short-circuits
    # on the first mismatched byte).
    if not x_internal_key or not hmac.compare_digest(x_internal_key, settings.internal_api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")
