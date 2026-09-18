"""single-row licence key store — 2026-09-18.

Holds the pasted licence key (if any). One row, id = 1. When absent or
invalid, the app falls back to the built-in default licence
(services/license.py), so a fresh install needs no key to run.

Revision ID: 0015_license_key
Revises: 0014_overtime_punch_types
Create Date: 2026-09-18
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_license_key"
down_revision = "0014_overtime_punch_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "license_key",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("installed_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("id = 1", name="ck_license_singleton"),
    )


def downgrade() -> None:
    op.drop_table("license_key")
