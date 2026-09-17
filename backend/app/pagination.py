from sqlalchemy import func
from sqlalchemy.orm import Query, Session

from app.schemas import Paginated


def paginate(db: Session, query: Query, page: int, page_size: int, serialize=lambda x: x) -> Paginated:
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    # Count via a wrapping subquery rather than `.with_entities(func.count())`
    # directly: on a query with no `.join()`, `with_entities(func.count())`
    # drops the implicit FROM clause entirely (`SELECT count(*)` with no
    # `FROM users`), which Postgres evaluates as a single-row scalar query and
    # always returns 1 regardless of actual row count. Wrapping in a subquery
    # preserves the FROM (and any joins/filters) unconditionally, so this is
    # correct for both joined and unjoined queries.
    total = db.query(func.count()).select_from(query.order_by(None).subquery()).scalar()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if total else 0
    return Paginated(
        items=[serialize(i) for i in items],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
    )
