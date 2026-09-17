"""device clock-drift tracking — 2026-09-17.

Every punch is timestamped by the DEVICE, so a terminal whose clock has
drifted produces lateness and overtime figures wrong by exactly that drift,
with nothing in the data to show it. This was not hypothetical: a
DS-K1T804AMF still set to its factory UTC+8 stamped events `+08:00` and
turned an on-time arrival into 61 minutes late.

The worker now reads each device's own clock on every sync and reports the
difference here; `GET /reports/alerts` raises `device_clock_drift` past the
tolerance.

Revision ID: 0012_device_clock_skew
Revises: 0011_split_shifts_ot_approval
Create Date: 2026-09-17

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0012_device_clock_skew"
down_revision = "0011_split_shifts_ot_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Seconds the device clock is AHEAD of the server (negative = behind).
    # NULL means "not measured" — either the vendor exposes no clock endpoint
    # (Hik-Connect) or the last read failed — which is deliberately distinct
    # from a measured zero.
    op.add_column("devices", sa.Column("clock_skew_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "devices", sa.Column("clock_checked_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("devices", "clock_checked_at")
    op.drop_column("devices", "clock_skew_seconds")
