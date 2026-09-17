from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_location_access, require_manager_or_admin
from app.models import AbsenceRuleConfig, OvertimeConfig, PenaltyConfig, User
from app.schemas import (
    AbsenceRuleConfigCreate,
    AbsenceRuleConfigOut,
    AbsenceRuleConfigUpdate,
    OvertimeConfigCreate,
    OvertimeConfigOut,
    OvertimeConfigUpdate,
    PenaltyConfigCreate,
    PenaltyConfigOut,
    PenaltyConfigUpdate,
)

router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(require_manager_or_admin)])


def _with_location_name(out, row):
    out.location_name = row.location.name if row.location else None
    return out


def _scope_manager(q, model, user: User):
    # A manager with payroll access sees their own location's configs plus
    # any org-wide (location_id is null) config that applies to them too —
    # but assert_location_access still blocks them from creating/editing a
    # global one (location_id None fails the "own location" check).
    if user.role == "manager":
        q = q.filter(or_(model.location_id == user.location_id, model.location_id.is_(None)))
    return q


# ---- Penalty ----


@router.get("/penalty", response_model=list[PenaltyConfigOut])
def list_penalty(location_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    q = _scope_manager(db.query(PenaltyConfig), PenaltyConfig, user)
    if location_id is not None:
        q = q.filter(PenaltyConfig.location_id == location_id)
    rows = q.order_by(PenaltyConfig.effective_from.desc()).all()
    return [_with_location_name(PenaltyConfigOut.model_validate(r), r) for r in rows]


@router.post("/penalty", response_model=PenaltyConfigOut, status_code=status.HTTP_201_CREATED)
def create_penalty(payload: PenaltyConfigCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    assert_location_access(user, payload.location_id)
    row = PenaltyConfig(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _with_location_name(PenaltyConfigOut.model_validate(row), row)


@router.get("/penalty/{config_id}", response_model=PenaltyConfigOut)
def get_penalty(config_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    row = db.get(PenaltyConfig, config_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Penalty config not found")
    if user.role == "manager" and row.location_id is not None:
        assert_location_access(user, row.location_id)
    return _with_location_name(PenaltyConfigOut.model_validate(row), row)


@router.put("/penalty/{config_id}", response_model=PenaltyConfigOut)
def update_penalty(config_id: int, payload: PenaltyConfigUpdate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    row = db.get(PenaltyConfig, config_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Penalty config not found")
    assert_location_access(user, row.location_id)
    data = payload.model_dump(exclude_unset=True)
    # SECURITY (SECURITY_REPORT.md Revision 3): re-check the *incoming*
    # location_id too, not just the row's current one. Without this a
    # manager can move one of their own configs onto another location — or
    # to location_id null, which makes it org-wide — and so rewrite pay
    # rules outside their scope. Mirrors devices.py/employees.py.
    if "location_id" in data:
        assert_location_access(user, data["location_id"])
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _with_location_name(PenaltyConfigOut.model_validate(row), row)


# ---- Overtime ----


@router.get("/overtime", response_model=list[OvertimeConfigOut])
def list_overtime(location_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    q = _scope_manager(db.query(OvertimeConfig), OvertimeConfig, user)
    if location_id is not None:
        q = q.filter(OvertimeConfig.location_id == location_id)
    rows = q.order_by(OvertimeConfig.effective_from.desc()).all()
    return [_with_location_name(OvertimeConfigOut.model_validate(r), r) for r in rows]


@router.post("/overtime", response_model=OvertimeConfigOut, status_code=status.HTTP_201_CREATED)
def create_overtime(payload: OvertimeConfigCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    assert_location_access(user, payload.location_id)
    row = OvertimeConfig(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _with_location_name(OvertimeConfigOut.model_validate(row), row)


@router.get("/overtime/{config_id}", response_model=OvertimeConfigOut)
def get_overtime(config_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    row = db.get(OvertimeConfig, config_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overtime config not found")
    if user.role == "manager" and row.location_id is not None:
        assert_location_access(user, row.location_id)
    return _with_location_name(OvertimeConfigOut.model_validate(row), row)


@router.put("/overtime/{config_id}", response_model=OvertimeConfigOut)
def update_overtime(config_id: int, payload: OvertimeConfigUpdate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    row = db.get(OvertimeConfig, config_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Overtime config not found")
    assert_location_access(user, row.location_id)
    data = payload.model_dump(exclude_unset=True)
    # SECURITY (SECURITY_REPORT.md Revision 3): re-check the *incoming*
    # location_id too, not just the row's current one. Without this a
    # manager can move one of their own configs onto another location — or
    # to location_id null, which makes it org-wide — and so rewrite pay
    # rules outside their scope. Mirrors devices.py/employees.py.
    if "location_id" in data:
        assert_location_access(user, data["location_id"])
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _with_location_name(OvertimeConfigOut.model_validate(row), row)


# ---- Absence rule ----


@router.get("/absence-rule", response_model=list[AbsenceRuleConfigOut])
def list_absence_rule(location_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    q = _scope_manager(db.query(AbsenceRuleConfig), AbsenceRuleConfig, user)
    if location_id is not None:
        q = q.filter(AbsenceRuleConfig.location_id == location_id)
    rows = q.order_by(AbsenceRuleConfig.effective_from.desc()).all()
    return [_with_location_name(AbsenceRuleConfigOut.model_validate(r), r) for r in rows]


@router.post("/absence-rule", response_model=AbsenceRuleConfigOut, status_code=status.HTTP_201_CREATED)
def create_absence_rule(payload: AbsenceRuleConfigCreate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    assert_location_access(user, payload.location_id)
    row = AbsenceRuleConfig(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _with_location_name(AbsenceRuleConfigOut.model_validate(row), row)


@router.get("/absence-rule/{config_id}", response_model=AbsenceRuleConfigOut)
def get_absence_rule(config_id: int, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    row = db.get(AbsenceRuleConfig, config_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Absence rule config not found")
    if user.role == "manager" and row.location_id is not None:
        assert_location_access(user, row.location_id)
    return _with_location_name(AbsenceRuleConfigOut.model_validate(row), row)


@router.put("/absence-rule/{config_id}", response_model=AbsenceRuleConfigOut)
def update_absence_rule(config_id: int, payload: AbsenceRuleConfigUpdate, db: Session = Depends(get_db), user: User = Depends(require_manager_or_admin)):
    row = db.get(AbsenceRuleConfig, config_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Absence rule config not found")
    assert_location_access(user, row.location_id)
    data = payload.model_dump(exclude_unset=True)
    # SECURITY (SECURITY_REPORT.md Revision 3): re-check the *incoming*
    # location_id too, not just the row's current one. Without this a
    # manager can move one of their own configs onto another location — or
    # to location_id null, which makes it org-wide — and so rewrite pay
    # rules outside their scope. Mirrors devices.py/employees.py.
    if "location_id" in data:
        assert_location_access(user, data["location_id"])
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return _with_location_name(AbsenceRuleConfigOut.model_validate(row), row)
