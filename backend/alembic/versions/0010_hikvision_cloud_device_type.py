"""allow devices.device_type = 'hikvision_cloud' — 2026-09-16. Second
connectivity path for Hikvision terminals: reached through Hikvision's
Hik-Connect Open Platform instead of directly over the LAN/DDNS address.
Same normalized punches either way; only the transport differs. See
BLUEPRINT.md Section 5.5 and worker/worker/adapters/hikvision_cloud.py.

Revision ID: 0010_hikvision_cloud_device_type
Revises: 0009_multi_vendor_devices
Create Date: 2026-09-16

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_hikvision_cloud_device_type"
down_revision = "0009_multi_vendor_devices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_device_type", "devices", type_="check")
    op.create_check_constraint(
        "ck_device_type", "devices", "device_type in ('zkteco','hikvision','hikvision_cloud')"
    )


def downgrade() -> None:
    # Any rows already using the cloud transport fall back to the direct
    # Hikvision adapter rather than blocking the downgrade — the device is
    # the same unit, only the transport differs, and its ip_address would
    # need to be repointed at the device itself by hand afterwards.
    op.execute("UPDATE devices SET device_type = 'hikvision' WHERE device_type = 'hikvision_cloud'")
    op.drop_constraint("ck_device_type", "devices", type_="check")
    op.create_check_constraint(
        "ck_device_type", "devices", "device_type in ('zkteco','hikvision')"
    )
