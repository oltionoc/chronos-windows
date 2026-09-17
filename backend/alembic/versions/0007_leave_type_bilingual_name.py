"""leave_types.name -> name_en + name_sq — 2026-08-25. The frontend is
bilingual (Albanian/English toggle) but leave type names were a single
free-text field, so they always showed in whatever language they were
typed in, regardless of the viewer's chosen UI language. Splits into two
required columns; existing rows are backfilled with the old value in both
until an admin fills in the real translation of the other.

Revision ID: 0007_leave_type_bilingual_name
Revises: 0006_drop_payslip_pdf_path
Create Date: 2026-08-25

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007_leave_type_bilingual_name"
down_revision = "0006_drop_payslip_pdf_path"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leave_types", sa.Column("name_en", sa.Text, nullable=True))
    op.add_column("leave_types", sa.Column("name_sq", sa.Text, nullable=True))
    op.execute("UPDATE leave_types SET name_en = name, name_sq = name")
    op.alter_column("leave_types", "name_en", nullable=False)
    op.alter_column("leave_types", "name_sq", nullable=False)
    op.drop_column("leave_types", "name")


def downgrade() -> None:
    op.add_column("leave_types", sa.Column("name", sa.Text, nullable=True))
    op.execute("UPDATE leave_types SET name = name_en")
    op.alter_column("leave_types", "name", nullable=False)
    op.drop_column("leave_types", "name_en")
    op.drop_column("leave_types", "name_sq")
