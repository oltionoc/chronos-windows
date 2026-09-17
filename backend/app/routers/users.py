"""Users (login accounts) — GAP RESOLUTION per FRONTEND_NOTES.md #3:
BLUEPRINT.md Section 4 has no `/users` CRUD section, but DESIGN_SPEC.md
Section 5.23 requires a full `/settings/users` management page and the
frontend already codes against `GET/POST /users`, `PATCH /users/{id}`,
`PATCH /users/{id}/reset-password`. Implemented here exactly at that
contract. HR/Admin only (account management is not a Manager capability
per BLUEPRINT.md Section 6.2).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_admin
from app.models import Location, User
from app.pagination import paginate
from app.schemas import AppUserCreate, AppUserOut, AppUserUpdate, Paginated, ResetPasswordRequest, Role
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])


def _serialize(user: User) -> AppUserOut:
    out = AppUserOut.model_validate(user)
    out.employee_name = f"{user.employee.first_name} {user.employee.last_name}" if user.employee else None
    out.location_name = user.location.name if user.location else None
    return out


@router.get("", response_model=Paginated[AppUserOut])
def list_users(role: Role | None = None, page: int = 1, page_size: int = 25, db: Session = Depends(get_db)):
    q = db.query(User)
    if role is not None:
        q = q.filter(User.role == role)
    q = q.order_by(User.username)
    return paginate(db, q, page, page_size, serialize=_serialize)


@router.post("", response_model=AppUserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: AppUserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    if payload.location_id is not None and db.get(Location, payload.location_id) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not found")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        employee_id=payload.employee_id,
        location_id=payload.location_id,
        is_active=payload.is_active,
        # SECURITY: HR/Admin chose this password on the user's behalf, so
        # force a change on first login — see SECURITY_REPORT.md.
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.patch("/{user_id}", response_model=AppUserOut)
def update_user(user_id: int, payload: AppUserUpdate, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("location_id") is not None and db.get(Location, data["location_id"]) is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Location not found")
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.patch("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(user_id: int, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.password_hash = hash_password(payload.new_password)
    # SECURITY: this is HR/Admin choosing a password on the user's behalf
    # (e.g. a reset), so force a change on next login — see SECURITY_REPORT.md.
    user.must_change_password = True
    db.commit()
