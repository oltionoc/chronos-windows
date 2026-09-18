"""Licence status and key installation.

`GET /license/status` is readable by any signed-in user (the frontend banner
and the expired-screen use it). `POST /license` (admin only) pastes a new
signed key; it is verified before being stored, and rejected if it would not
extend the term. Both stay reachable when the licence has expired — see the
gate in app/main.py — so an admin can always sign in and paste a new key.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_admin
from app.models import LicenseKey, User
from app.schemas import LicenseInstall, LicenseStatusOut
from app.services.license import LicenseError, effective_license, license_status, parse_license

router = APIRouter(prefix="/license", tags=["license"])


def _stored_key(db: Session) -> str | None:
    row = db.get(LicenseKey, 1)
    return row.key if row else None


@router.get("/status", response_model=LicenseStatusOut, dependencies=[Depends(get_current_user)])
def get_status(db: Session = Depends(get_db)):
    return license_status(_stored_key(db))


@router.post("/status", response_model=LicenseStatusOut)
def install_key(
    payload: LicenseInstall,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    try:
        new = parse_license(payload.key)
    except LicenseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Must not shorten the term below what is already in force.
    current = effective_license(_stored_key(db))
    if new.expires < current.expires:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This licence key expires earlier than the one already installed.",
        )

    row = db.get(LicenseKey, 1)
    if row is None:
        row = LicenseKey(id=1, key=payload.key.strip(), installed_by_user_id=user.id)
        db.add(row)
    else:
        row.key = payload.key.strip()
        row.installed_by_user_id = user.id
    db.commit()
    return license_status(payload.key.strip())
