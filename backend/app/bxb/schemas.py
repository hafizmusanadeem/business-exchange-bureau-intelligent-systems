"""API schemas for the BXB routes.

Kept apart from the table models so the public contract can change without
touching the database layer.
"""
from __future__ import annotations

from datetime import date

from pydantic import model_validator
from sqlmodel import Field, SQLModel

from app.bxb.models import InvestorProfileBase, ListingBase, ListingStatus


class ListingPublic(ListingBase):
    """What the marketplace may show about a listing.

    Deliberately has no ``owner_id``: sellers can be anonymous, and a response
    model is the only thing standing between a table row and the wire.
    """

    id: int
    status: ListingStatus
    listed_on: date
    closed_on: date | None = None


class ListingsPublic(SQLModel):
    count: int
    data: list[ListingPublic]


class InvestorProfileIn(InvestorProfileBase):
    """Single JSON body for POST /bxb/investors/me.

    Before, ``sectors`` and ``emirates`` were bare ``list[str]`` parameters next to a
    body model, which FastAPI treats as a second body field and forces an
    awkward ``{"body": {...}, "sectors": [...]}`` payload.
    """

    sectors: list[str] = Field(default_factory=list, max_length=20)
    emirates: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _budget_range(self) -> "InvestorProfileIn":
        if self.budget_max < self.budget_min:
            raise ValueError("budget_max must be >= budget_min")
        return self
