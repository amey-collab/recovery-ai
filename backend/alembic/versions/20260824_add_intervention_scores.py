"""add intervention score persistence

Revision ID: 20260824_intervention_scores
Revises:
Create Date: 2026-08-24

This is intentionally additive. Existing payment/recovery data is not touched.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_intervention_scores"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The deployment may already contain tables created by the development
    # bootstrap. Only the newly introduced table is owned by this revision.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "intervention_scores" not in inspector.get_table_names():
        op.create_table(
            "intervention_scores",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("payment_id", sa.Integer(), nullable=False),
            sa.Column("scores", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_intervention_scores_payment_id",
            "intervention_scores",
            ["payment_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "intervention_scores" in sa.inspect(bind).get_table_names():
        op.drop_index("ix_intervention_scores_payment_id", table_name="intervention_scores")
        op.drop_table("intervention_scores")
