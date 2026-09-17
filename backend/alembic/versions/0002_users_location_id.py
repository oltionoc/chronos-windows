"""add users.location_id — 2026-08-22 access-control change (BLUEPRINT.md
Section 3.14 / 6.2 / 6.4): manager visibility moves from team-based
(employees.manager_user_id) to location-based (users.location_id ==
employees.location_id) scoping.

Nullable, no backfill/default — existing rows get NULL, which is the
correct starting state (managers see nothing until HR assigns a location).
employees.manager_user_id is untouched; it remains display-only.

Revision ID: 0002_users_location_id
Revises: 0001_initial
Create Date: 2026-08-22

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_users_location_id"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("location_id", sa.Integer, nullable=True))
    op.create_foreign_key(
        "fk_users_location_id", "users", "locations", ["location_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_location_id", "users", type_="foreignkey")
    op.drop_column("users", "location_id")
