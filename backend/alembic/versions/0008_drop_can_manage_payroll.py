"""drop users.can_manage_payroll — 2026-08-25. The per-manager payroll/config
opt-in flag is removed per client direction: managers now get total access
(operational + payroll + config) for their own location, automatically, no
per-manager grant needed. See app/deps.py require_manager_or_admin.

Revision ID: 0008_drop_can_manage_payroll
Revises: 0007_leave_type_bilingual_name
Create Date: 2026-08-25

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0008_drop_can_manage_payroll"
down_revision = "0007_leave_type_bilingual_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "can_manage_payroll")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("can_manage_payroll", sa.Boolean, nullable=False, server_default="false"),
    )
