"""rename role 'hr_admin' -> 'admin' — 2026-08-24 terminology change (no
functional/permission change, same role, just the value/label). Existing
databases already have the old constraint and old data from when 0001 first
ran; editing 0001's source text doesn't retroactively change either on a
database that's already migrated, hence this migration.

Revision ID: 0004_role_admin_rename
Revises: 0003_employees_job_title
Create Date: 2026-08-24

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0004_role_admin_rename"
down_revision = "0003_employees_job_title"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Constraint must be dropped BEFORE the data update — the old constraint
    # (role in ('hr_admin','manager')) would reject 'admin' rows otherwise.
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute(sa.text("UPDATE users SET role = 'admin' WHERE role = 'hr_admin'"))
    op.create_check_constraint("ck_users_role", "users", "role in ('admin','manager')")


def downgrade() -> None:
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.execute(sa.text("UPDATE users SET role = 'hr_admin' WHERE role = 'admin'"))
    op.create_check_constraint("ck_users_role", "users", "role in ('hr_admin','manager')")
