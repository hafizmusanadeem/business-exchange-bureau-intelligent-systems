"""BXB Grounded AI Reports routes (Module 6).

Register in app/api/main.py:

    from app.api.routes import bxb_reports
    api_router.include_router(bxb_reports.router)

GET /bxb/reports/market?q_from=&q_to=[&as_of=][&writer=template|llm][&format=json|markdown]
The default writer is deterministic. `writer=llm` needs ANTHROPIC_API_KEY and
BXB_LLM_ENABLED=1; the verifier and template fallback apply either way, so
published text is always grounded. Reports describe this marketplace's records only."""
import os
from datetime import date
from typing import Any
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from sqlmodel import select
from app.api.deps import CurrentUser, SessionDep
from app.bxb import report_facts as RF, report_writer as W, sentiment as S
from app.bxb.models import InvestorEvent, InvestorProfile, Listing, ListingStatus

router = APIRouter(prefix="/bxb/reports", tags=["bxb-reports"])


@router.get("/market")
def market_report(session: SessionDep, user: CurrentUser, q_from: str, q_to: str, as_of: date | None = None, writer: str = "template", format: str = "json") -> Any:
    for q in (q_from, q_to):
        try: S.quarter_bounds(q)
        except Exception: raise HTTPException(422, "Quarters must look like 2026-Q2")
    events = [e.model_dump() for e in session.exec(select(InvestorEvent).where(InvestorEvent.qualified == True))]  # noqa: E712
    investors = {p.id: p.model_dump() for p in session.exec(select(InvestorProfile))}
    listings = [l.model_dump() | {"status": l.status.value} for l in session.exec(select(Listing)) if l.status != ListingStatus.draft]
    facts = RF.collect_facts(events, listings, investors, q_from, q_to, as_of or date.today())
    llm = None
    if writer == "llm":
        if os.getenv("BXB_LLM_ENABLED") != "1": raise HTTPException(400, "LLM writer is not enabled on this server")
        llm = W.anthropic_llm()
    rep = W.generate(facts, llm)
    if format == "markdown": return PlainTextResponse(W.render_markdown(rep), media_type="text/markdown")
    return {**rep, "facts": facts}
