"""add employees.job_title — free-text position/role label for display and
filtering. Nullable, no backfill (existing rows get NULL, shown as "—").

Revision ID: 0003_employees_job_title
Revises: 0002_users_location_id
Create Date: 2026-08-22

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0003_employees_job_title"
down_revision = "0002_users_location_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("job_title", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("employees", "job_title")
