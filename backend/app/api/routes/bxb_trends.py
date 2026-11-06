"""BXB Sale Trends, Demand vs Supply & Forecast routes (Module 3).

Register in app/api/main.py:

    from app.api.routes import bxb_trends
    api_router.include_router(bxb_trends.router)
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import SessionDep
from app.bxb import forecast as F, sentiment as S, trends as T
from app.bxb.models import InvestorEvent, Listing, ListingStatus

router = APIRouter(prefix="/bxb/trends", tags=["bxb-trends"])
_OPEN = {ListingStatus.draft}


def _listings(session):
    return [
        l.model_dump() | {"status": l.status.value}
        for l in session.exec(select(Listing))
        if l.status not in _OPEN
    ]


def _events(session):
    return [
        e.model_dump()
        for e in session.exec(
            select(InvestorEvent).where(InvestorEvent.qualified == True)  # noqa: E712
        )
    ]


@router.get("/market")
def market(
    session: SessionDep,
    sector: str | None = None,
    as_of: date | None = None,
) -> Any:
    return T.market_stats(
        _listings(session), _events(session), as_of or date.today(), sector
    )


@router.get("/geography")
def geography(session: SessionDep, as_of: date | None = None) -> Any:
    return T.geography(_listings(session), as_of or date.today())


@router.get("/demand-supply")
def demand_supply(session: SessionDep, quarter: str) -> Any:
    try:
        S.quarter_bounds(quarter)
    except Exception:
        raise HTTPException(422, "Quarter must look like 2026-Q2")
    return T.demand_vs_supply(_listings(session), _events(session), quarter)


@router.get("/forecast")
def forecast(
    session: SessionDep,
    sector: str | None = None,
    metric: str = "new_listings",
    horizon: int = 6,
) -> Any:
    if metric not in ("new_listings", "median_asking"):
        raise HTTPException(422, "metric: new_listings | median_asking")
    series = T.monthly_series(_listings(session), sector, metric)
    return {
        "sector": sector or "All",
        "metric": metric,
        "history": series[-12:],
        **F.forecast([v for _, v in series], min(horizon, 12)),
    }
