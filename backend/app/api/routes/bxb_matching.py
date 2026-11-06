"""BXB Investor Matching routes (Module 4).

Register in app/api/main.py:

    from app.api.routes import bxb_matching
    api_router.include_router(bxb_matching.router)

Add `scikit-learn`, `numpy` and `joblib` to backend/pyproject.toml.
Train from real events with matching.pairs_from_events + LearnedScorer.fit(...).save(path);
until then the transparent rule scorer is used.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.bxb import matching as M
from app.bxb.models import InvestorProfile, Listing

router = APIRouter(prefix="/bxb/matching", tags=["bxb-matching"])
MODEL_PATH = os.getenv("BXB_MATCHER_PATH", "models/matcher.joblib")


@lru_cache(maxsize=1)
def _scorer():
    return (
        M.LearnedScorer.load(MODEL_PATH)
        if os.path.exists(MODEL_PATH)
        else M.RuleScorer()
    )


@router.get("/listing/{listing_id}")
def match_listing(
    listing_id: int, session: SessionDep, user: CurrentUser, k: int = 10
) -> Any:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    if not user.is_superuser and listing.owner_id != user.id:
        raise HTTPException(403, "Only the seller or a BXB admin can see matches")
    invs = [p.model_dump() for p in session.exec(select(InvestorProfile))]
    return M.rank_investors(listing.model_dump(), invs, _scorer(), min(k, 50))
