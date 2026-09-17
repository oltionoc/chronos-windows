"""multi-vendor device support — 2026-09-16. The product now needs to talk
to more than the original ZKTeco K40 (a Hikvision DS-K1T804BEF is the next
real device). Widens devices.ip_address to accept a hostname (Postgres INET
rejects "foo.ddns.net" — the client's new device is reachable via cloud/DDNS,
not always a static LAN IP), adds devices.device_type + auth credentials for
HTTP/ISAPI-style vendors, and adds attendance_logs.punch_type_hint so a
vendor that already tells us the punch kind (Hikvision's attendanceStatus)
doesn't have to go through ZKTeco's alternating-parity heuristic.

Revision ID: 0009_multi_vendor_devices
Revises: 0008_drop_can_manage_payroll
Create Date: 2026-09-16

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0009_multi_vendor_devices"
down_revision = "0008_drop_can_manage_payroll"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "devices",
        "ip_address",
        type_=sa.Text(),
        postgresql_using="ip_address::text",
    )
    op.add_column(
        "devices",
        sa.Column("device_type", sa.Text(), nullable=False, server_default="zkteco"),
    )
    op.create_check_constraint(
        "ck_device_type", "devices", "device_type in ('zkteco','hikvision')"
    )
    op.add_column("devices", sa.Column("auth_username", sa.Text(), nullable=True))
    op.add_column("devices", sa.Column("auth_password", sa.Text(), nullable=True))

    op.add_column("attendance_logs", sa.Column("punch_type_hint", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_punch_type_hint",
        "attendance_logs",
        "punch_type_hint in ('check_in_work','check_out_work','check_in_break','check_out_break') "
        "or punch_type_hint is null",
    )


def downgrade() -> None:
    op.drop_constraint("ck_punch_type_hint", "attendance_logs", type_="check")
    op.drop_column("attendance_logs", "punch_type_hint")

    op.drop_column("devices", "auth_password")
    op.drop_column("devices", "auth_username")
    op.drop_constraint("ck_device_type", "devices", type_="check")
    op.drop_column("devices", "device_type")
    op.alter_column(
        "devices",
        "ip_address",
        type_=sa.dialects.postgresql.INET(),
        postgresql_using="ip_address::inet",
    )
