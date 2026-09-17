import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas import ChangePasswordRequest, CurrentUser, LoginRequest
from app.security import COOKIE_NAME, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# SECURITY: minimal in-memory login throttle (see SECURITY_REPORT.md "no
# brute-force protection on login"). Keyed by username so a single account
# can't be brute-forced regardless of source IP. Intentionally simple (no
# extra dependency) — adequate for the Phase 1 single-process LAN deployment.
# NOTE: state is per-process and resets on restart; does not share state
# across multiple uvicorn workers/replicas — flagged as a residual limitation
# in SECURITY_REPORT.md for any future horizontally-scaled deployment.
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 15 * 60
_login_attempts: dict[str, list[float]] = {}


def _login_rate_limit_check(username: str) -> None:
    key = username.strip().lower()
    now = time.monotonic()
    window_start = now - _LOGIN_WINDOW_SECONDS
    attempts = [t for t in _login_attempts.get(key, []) if t > window_start]
    _login_attempts[key] = attempts
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts for this account. Try again later.",
        )


def _login_rate_limit_record(username: str) -> None:
    key = username.strip().lower()
    _login_attempts.setdefault(key, []).append(time.monotonic())


def _login_rate_limit_clear(username: str) -> None:
    _login_attempts.pop(username.strip().lower(), None)


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    _login_rate_limit_check(payload.username)

    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        _login_rate_limit_record(payload.username)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    _login_rate_limit_clear(payload.username)

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(user.id, user.role)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_expiry_hours * 3600,
        path="/",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, user: User = Depends(get_current_user)):
    response.delete_cookie(key=COOKIE_NAME, path="/")


@router.get("/me", response_model=CurrentUser)
def me(user: User = Depends(get_current_user)):
    out = CurrentUser.model_validate(user)
    out.employee_name = f"{user.employee.first_name} {user.employee.last_name}" if user.employee else None
    out.location_name = user.location.name if user.location else None
    return out


@router.patch("/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
