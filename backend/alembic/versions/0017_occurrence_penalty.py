"""per-occurrence penalties + break penalties — 2026-09-19.

The client penalises lateness OR early departure, at WORK OR BREAK, at a flat
amount for EACH occurrence (e.g. 5 EUR per event), not per minute or per day.
This adds:

  * penalty rule_type 'flat_per_occurrence' — penalty = occurrences x flat_amount_eur.
  * attendance_daily_status.penalty_occurrences — how many chargeable events
    happened that day: late to work, early from work, and a break that ran
    long (returned late), counted 1 each. Break violations were not penalised
    at all before.

Revision ID: 0017_occurrence_penalty
Revises: 0016_rota
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_occurrence_penalty"
down_revision = "0016_rota"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attendance_daily_status",
        sa.Column("penalty_occurrences", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_constraint("ck_penalty_rule_type", "penalty_config", type_="check")
    op.create_check_constraint(
        "ck_penalty_rule_type",
        "penalty_config",
        "rule_type in ('flat_per_minute','threshold_allowance','flat_per_occurrence')",
    )


def downgrade() -> None:
    op.execute("UPDATE penalty_config SET rule_type = 'threshold_allowance' WHERE rule_type = 'flat_per_occurrence'")
    op.drop_constraint("ck_penalty_rule_type", "penalty_config", type_="check")
    op.create_check_constraint(
        "ck_penalty_rule_type", "penalty_config", "rule_type in ('flat_per_minute','threshold_allowance')"
    )
    op.drop_column("attendance_daily_status", "penalty_occurrences")
