"""BXB foundation routes.

Register in app/api/main.py:

    from app.api.routes import bxb
    api_router.include_router(bxb.router)
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import col, func, select

from app.api.deps import CurrentUser, SessionDep
from app.bxb.models import (
    QUALIFIED,
    EventKind,
    InvestorEvent,
    InvestorProfile,
    Listing,
    ListingBase,
    ListingStatus,
)
from app.bxb.schemas import InvestorProfileIn, ListingPublic, ListingsPublic

router = APIRouter(prefix="/bxb", tags=["bxb"])


@router.get("/listings", response_model=ListingsPublic)
def list_listings(
    session: SessionDep,
    sector: str | None = None,
    emirate: str | None = None,
    min_price: int | None = None,
    max_price: int | None = None,
    min_ebitda: int | None = None,
    skip: int = 0,
    limit: int = 50,
) -> Any:
    q = select(Listing).where(Listing.status == ListingStatus.active)
    if sector:
        q = q.where(Listing.sector == sector)
    if emirate:
        q = q.where(Listing.emirate == emirate)
    if min_price is not None:
        q = q.where(Listing.asking_price >= min_price)
    if max_price is not None:
        q = q.where(Listing.asking_price <= max_price)
    if min_ebitda is not None:
        q = q.where(Listing.ebitda >= min_ebitda)
    total = session.exec(select(func.count()).select_from(q.subquery())).one()
    rows = session.exec(
        q.order_by(col(Listing.listed_on).desc())
        .offset(skip)
        .limit(min(limit, 200))
    ).all()
    return {"count": total, "data": rows}


@router.post("/listings", response_model=ListingPublic)
def create_listing(
    session: SessionDep, user: CurrentUser, body: ListingBase
) -> Any:
    item = Listing.model_validate(
        body, update={"owner_id": user.id, "status": ListingStatus.draft}
    )
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.patch("/listings/{listing_id}/status", response_model=ListingPublic)
def set_status(
    listing_id: int,
    status: ListingStatus,
    session: SessionDep,
    user: CurrentUser,
) -> Any:
    item = session.get(Listing, listing_id)
    if not item:
        raise HTTPException(404, "Listing not found")
    # Sellers manage their own listings; superusers (BXB admins) approve any listing.
    if not user.is_superuser and item.owner_id != user.id:
        raise HTTPException(403, "Not allowed")
    if status == ListingStatus.active and not user.is_superuser:
        raise HTTPException(403, "Admin approval required")
    item.status = status
    if status in (ListingStatus.sold, ListingStatus.expired):
        item.closed_on = date.today()
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@router.post("/investors/me", response_model=InvestorProfile)
def upsert_my_profile(
    session: SessionDep,
    user: CurrentUser,
    body: InvestorProfileIn,
) -> Any:
    prof = session.exec(
        select(InvestorProfile).where(InvestorProfile.user_id == user.id)
    ).first()
    data = body.model_dump()
    if prof:
        prof.sqlmodel_update(data)
    else:
        prof = InvestorProfile(**data, user_id=user.id)
    session.add(prof)
    session.commit()
    session.refresh(prof)
    return prof


@router.post("/events", response_model=InvestorEvent)
def record_event(
    session: SessionDep,
    user: CurrentUser,
    listing_id: int,
    kind: EventKind,
) -> Any:
    prof = session.exec(
        select(InvestorProfile).where(InvestorProfile.user_id == user.id)
    ).first()
    listing = session.get(Listing, listing_id)
    if not prof or not listing:
        raise HTTPException(404, "Investor profile or listing not found")
    ev = InvestorEvent(
        investor_id=prof.id,
        listing_id=listing.id,
        sector=listing.sector,
        kind=kind,
        qualified=kind in QUALIFIED,
    )
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev