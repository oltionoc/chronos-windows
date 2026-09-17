"""Effective-dated config row lookup — shared by nightly recompute and
payroll aggregation (BLUEPRINT.md Sections 3.11-3.13, 5.5).

Picks the row whose [effective_from, effective_to) window covers the given
date, preferring a location-specific row over a location_id=NULL ("applies
to all locations") row, and the most recently effective row on ties.
"""
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session


def get_effective_config(db: Session, model, location_id: int | None, on_date: date):
    stmt = (
        select(model)
        .where(
            model.is_active.is_(True),
            model.effective_from <= on_date,
            (model.effective_to.is_(None)) | (model.effective_to > on_date),
        )
        .where((model.location_id == location_id) | (model.location_id.is_(None)))
        .order_by(
            # `location_id = :loc` is NULL (not false) for an org-wide row,
            # and Postgres orders DESC as NULLS FIRST — so the org-wide row
            # outranked the location-specific one, the exact inverse of the
            # rule documented above. Ordering on `IS NULL` instead yields a
            # real boolean: false (location-specific) sorts ahead of true.
            model.location_id.is_(None),
            model.effective_from.desc(),
        )
    )
    return db.execute(stmt).scalars().first()
