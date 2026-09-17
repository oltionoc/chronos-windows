"""drop payroll_run_lines.payslip_pdf_path — 2026-08-25, PDF payslip/export
removed entirely (WeasyPrint output was rendering as a blank/black page for
the client; replaced with an on-demand Excel payslip export instead, see
services/excel.py generate_payslip_xlsx).

Revision ID: 0006_drop_payslip_pdf_path
Revises: 0005_manager_payroll_access
Create Date: 2026-08-25

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0006_drop_payslip_pdf_path"
down_revision = "0005_manager_payroll_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("payroll_run_lines", "payslip_pdf_path")


def downgrade() -> None:
    op.add_column(
        "payroll_run_lines",
        sa.Column("payslip_pdf_path", sa.Text, nullable=True),
    )
