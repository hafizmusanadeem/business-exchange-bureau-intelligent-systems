"""Add FinancialFact table (Module 5: financial intelligence).

Revision ID: 2026_11_06_0002
Revises: 2026_11_06_0001
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2026_11_06_0002"
down_revision: Union[str, None] = "2026_11_06_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "financialfact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=40), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("raw", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("table_index", sa.Integer(), nullable=False),
        sa.Column("row", sa.Integer(), nullable=False),
        sa.Column("col", sa.Integer(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("scale", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("mapped_by", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listing.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_financialfact_listing_id"), "financialfact", ["listing_id"], unique=False)
    op.create_index(op.f("ix_financialfact_metric"), "financialfact", ["metric"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_financialfact_metric"), table_name="financialfact")
    op.drop_index(op.f("ix_financialfact_listing_id"), table_name="financialfact")
    op.drop_table("financialfact")
