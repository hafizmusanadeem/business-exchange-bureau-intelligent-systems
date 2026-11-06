"""BXB Investor Sentiment routes (Module 2).

Register in app/api/main.py:

    from app.api.routes import bxb_sentiment
    api_router.include_router(bxb_sentiment.router)

MVP loads qualified events into memory; at BXB scale, push the grouping into
SQL or a materialised view.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import SessionDep
from app.bxb import sentiment as S
from app.bxb.models import InvestorEvent, InvestorProfile

router = APIRouter(prefix="/bxb/sentiment", tags=["bxb-sentiment"])


def _load(session):
    ev = [e.model_dump() for e in session.exec(select(InvestorEvent).where(InvestorEvent.qualified == True))]  # noqa: E712
    inv = {p.id: p.model_dump() for p in session.exec(select(InvestorProfile))}
    return ev, inv


def _q(q: str) -> str:
    try: S.quarter_bounds(q)
    except Exception: raise HTTPException(422, "Quarter must look like 2026-Q2")
    return q


@router.get("/sectors")
def sectors(session: SessionDep, quarter: str) -> Any:
    ev, _ = _load(session)
    return S.sector_shares(ev, *S.quarter_bounds(_q(quarter)))

@router.get("/trend")
def trend(session: SessionDep, q_from: str, q_to: str) -> Any:
    ev, _ = _load(session)
    return S.trend(ev, _q(q_from), _q(q_to))

@router.get("/countries")
def countries(session: SessionDep, quarter: str) -> Any:
    ev, inv = _load(session)
    return S.country_mix(ev, inv, *S.quarter_bounds(_q(quarter)))

@router.get("/segments")
def segments(session: SessionDep, quarter: str) -> Any:
    ev, inv = _load(session)
    return S.segments(ev, inv, *S.quarter_bounds(_q(quarter)))

@router.get("/facts")
def facts(session: SessionDep, q_from: str, q_to: str) -> Any:
    ev, inv = _load(session)
    return S.facts(ev, inv, _q(q_from), _q(q_to))
