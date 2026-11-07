"""Request bodies for the AI cost-reduction routes (Module 8). Kept apart from the table models, like schemas.py."""
from __future__ import annotations

from sqlmodel import Field, SQLModel

from app.bxb.models import ListingBase


class ListingDraftIn(ListingBase):
    """A listing about to be submitted, plus fields the table does not store but moderation needs."""

    description: str = Field(default="", max_length=4000)
    employees: int | None = Field(default=None, ge=0, le=1_000_000)
    image_sha256: str | None = Field(default=None, max_length=64)


class FeasibilityIn(ListingBase):
    """A business that is not listed yet (for example a prospect for the Business Sale Service)."""

    guarantee: int = Field(default=3, ge=1, le=20)


class ReviewIn(SQLModel):
    decision: str = Field(max_length=10)  # "approve" | "reject"
    reviewer: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=1000)


class VerifyIn(SQLModel):
    sentence: str = Field(min_length=1, max_length=600)
