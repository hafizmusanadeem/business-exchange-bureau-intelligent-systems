"""BXB tables. Import this module from app/models.py (or alembic env) so Alembic
autogenerate sees the tables.

Replaces the template's sample Item model with Listing, InvestorProfile and
InvestorEvent (the richer event stream used by Investor Sentiment).
"""
from __future__ import annotations

import uuid
from datetime import date
from enum import Enum

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Role(str, Enum):
    seller = "seller"
    investor = "investor"
    admin = "admin"


class ListingStatus(str, Enum):
    draft = "draft"
    active = "active"
    under_offer = "under_offer"
    sold = "sold"
    expired = "expired"


class EventKind(str, Enum):
    view = "view"          # NOT counted as demand
    save = "save"
    enquiry = "enquiry"    # qualified
    meeting = "meeting"    # qualified
    offer = "offer"        # qualified


QUALIFIED = {EventKind.enquiry, EventKind.meeting, EventKind.offer}


class User(SQLModel, table=True):
    """Minimal account row so the foreign keys below resolve in this standalone repo.

    Same columns as the full-stack-fastapi-template User, so it stays compatible if you
    later move to the template. There is no login route yet: see app/api/deps.py.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    hashed_password: str
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True
    is_superuser: bool = False


class Profile(SQLModel, table=True):
    """Links a User to a BXB role. One row per user."""
    user_id: uuid.UUID = Field(
        foreign_key="user.id", primary_key=True, ondelete="CASCADE"
    )
    role: Role = Role.investor


class ListingBase(SQLModel):
    sector: str = Field(index=True, max_length=80)
    emirate: str = Field(index=True, max_length=40)
    years_operating: int = Field(ge=0, le=100)
    annual_revenue: int = Field(ge=0)
    ebitda: int
    asking_price: int = Field(ge=0)
    ownership_pct: int = Field(default=100, ge=1, le=100)
    anonymous: bool = True  # BXB sellers can stay anonymous


class Listing(ListingBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_id: uuid.UUID | None = Field(default=None, foreign_key="user.id")
    status: ListingStatus = Field(default=ListingStatus.draft, index=True)
    listed_on: date = Field(default_factory=date.today, index=True)
    closed_on: date | None = None


class InvestorProfileBase(SQLModel):
    name: str = Field(max_length=120)
    country: str = Field(index=True, max_length=60)
    budget_min: int = Field(ge=0)
    budget_max: int = Field(ge=0)
    min_ebitda: int = 0
    risk_appetite: str = "medium"  # low | medium | high


class InvestorProfile(InvestorProfileBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id")
    sectors: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    emirates: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    joined_on: date = Field(default_factory=date.today)


class InvestorEvent(SQLModel, table=True):
    """Observed behaviour. Sentiment (Module 2) counts only qualified events."""
    id: int | None = Field(default=None, primary_key=True)
    investor_id: int = Field(foreign_key="investorprofile.id", index=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    sector: str = Field(index=True, max_length=80)  # denormalised for fast aggregation
    kind: EventKind
    qualified: bool = Field(index=True)
    occurred_on: date = Field(default_factory=date.today, index=True)


class FinancialFact(SQLModel, table=True):
    """One extracted figure with full provenance (Module 5).

    Never edited in place: corrections add a new row.
    """

    id: int | None = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    metric: str = Field(index=True, max_length=40)
    period: str = Field(max_length=10)
    value: float
    raw: str = Field(max_length=80)
    label: str = Field(max_length=160)
    file_name: str = Field(max_length=200)
    page: int
    table_index: int
    row: int
    col: int
    bbox: list[float] | None = Field(default=None, sa_column=Column(JSON))
    scale: float = 1.0
    confidence: float = 1.0
    mapped_by: str = "rules"
