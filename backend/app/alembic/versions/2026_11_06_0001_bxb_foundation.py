"""BXB foundation tables: Profile, Listing, InvestorProfile, InvestorEvent.

Revision ID: 2026_11_06_0001
Revises: (none, this is the first revision in this repo)
Create Date: 2026-11-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# The models use native PostgreSQL enums (SQLModel's default), and the psycopg driver casts
# bind parameters to them, so these columns must be real enum types, not VARCHAR.
# Member NAMES are what SQLAlchemy stores; they equal the values in app/bxb/models.py.
ROLE = ("seller", "investor", "admin")
LISTING_STATUS = ("draft", "active", "under_offer", "sold", "expired")
EVENT_KIND = ("view", "save", "enquiry", "meeting", "offer")

# revision identifiers, used by Alembic.
revision: str = "2026_11_06_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The foreign keys below point at "user".id. In this standalone repo nothing else
    # creates that table, so create it here; skip it if a template already did.
    if not sa.inspect(op.get_bind()).has_table("user"):
        op.create_table(
            "user",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("full_name", sa.String(length=255), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("is_superuser", sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    op.create_table(
        "profile",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Enum(*ROLE, name="role"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "listing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sector", sa.String(length=80), nullable=False),
        sa.Column("emirate", sa.String(length=40), nullable=False),
        sa.Column("years_operating", sa.Integer(), nullable=False),
        sa.Column("annual_revenue", sa.Integer(), nullable=False),
        sa.Column("ebitda", sa.Integer(), nullable=False),
        sa.Column("asking_price", sa.Integer(), nullable=False),
        sa.Column("ownership_pct", sa.Integer(), nullable=False),
        sa.Column("anonymous", sa.Boolean(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Enum(*LISTING_STATUS, name="listingstatus"), nullable=False),
        sa.Column("listed_on", sa.Date(), nullable=False),
        sa.Column("closed_on", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_listing_sector"), "listing", ["sector"], unique=False)
    op.create_index(op.f("ix_listing_emirate"), "listing", ["emirate"], unique=False)
    op.create_index(op.f("ix_listing_status"), "listing", ["status"], unique=False)
    op.create_index(op.f("ix_listing_listed_on"), "listing", ["listed_on"], unique=False)

    op.create_table(
        "investorprofile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("country", sa.String(length=60), nullable=False),
        sa.Column("budget_min", sa.Integer(), nullable=False),
        sa.Column("budget_max", sa.Integer(), nullable=False),
        sa.Column("min_ebitda", sa.Integer(), nullable=False),
        sa.Column("risk_appetite", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("sectors", sa.JSON(), nullable=True),
        sa.Column("emirates", sa.JSON(), nullable=True),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_investorprofile_country"), "investorprofile", ["country"], unique=False
    )

    op.create_table(
        "investorevent",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("investor_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("sector", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.Enum(*EVENT_KIND, name="eventkind"), nullable=False),
        sa.Column("qualified", sa.Boolean(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["investor_id"], ["investorprofile.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["listing.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_investorevent_investor_id"), "investorevent", ["investor_id"], unique=False
    )
    op.create_index(
        op.f("ix_investorevent_listing_id"), "investorevent", ["listing_id"], unique=False
    )
    op.create_index(
        op.f("ix_investorevent_sector"), "investorevent", ["sector"], unique=False
    )
    op.create_index(
        op.f("ix_investorevent_qualified"), "investorevent", ["qualified"], unique=False
    )
    op.create_index(
        op.f("ix_investorevent_occurred_on"), "investorevent", ["occurred_on"], unique=False
    )


def downgrade() -> None:
    op.drop_table("investorevent")
    op.drop_table("investorprofile")
    op.drop_table("listing")
    op.drop_table("profile")
    bind = op.get_bind()
    for name in ("eventkind", "listingstatus", "role"):
        sa.Enum(name=name).drop(bind, checkfirst=True)
    # "user" is deliberately left in place: it may belong to a template or hold accounts.
