"""add users.can_manage_payroll — 2026-08-24 access-control change. Managers
get operational write access (employees/shift-schedules/devices) for their
own location by default (enforced in code, no schema flag needed for that
part); payroll/config access stays behind this explicit per-manager grant.

Revision ID: 0005_manager_payroll_access
Revises: 0004_role_admin_rename
Create Date: 2026-08-24

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0005_manager_payroll_access"
down_revision = "0004_role_admin_rename"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_manage_payroll", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "can_manage_payroll")
