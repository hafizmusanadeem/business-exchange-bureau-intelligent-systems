"""Read-only endpoints the frontend needs on top of the foundation routes.

Register in app/main.py:

    from app.api.routes import bxb_public
    app.include_router(bxb_public.router)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import func, select

from app.api.deps import SessionDep
from app.bxb.models import Listing, ListingStatus
from app.bxb.schemas import ListingPublic

router = APIRouter(prefix="/bxb", tags=["bxb-public"])


@router.get("/facets")
def facets(session: SessionDep) -> Any:
    """Filter options and headline count for active listings."""
    active = Listing.status == ListingStatus.active
    sectors = session.exec(
        select(Listing.sector).where(active).distinct().order_by(Listing.sector)
    ).all()
    emirates = session.exec(
        select(Listing.emirate).where(active).distinct().order_by(Listing.emirate)
    ).all()
    total = session.exec(select(func.count()).select_from(Listing).where(active)).one()
    return {"sectors": sectors, "emirates": emirates, "active_listings": total}


@router.get("/listings/{listing_id}", response_model=ListingPublic)
def get_listing(listing_id: int, session: SessionDep) -> Any:
    """One listing for the deal room. Drafts are never public."""
    item = session.get(Listing, listing_id)
    if not item or item.status == ListingStatus.draft:
        raise HTTPException(404, "Listing not found")
    return item
