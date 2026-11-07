"""BXB AI cost-reduction routes (Module 8).

Register in app/main.py (or app/api/main.py):

    from app.api.routes import bxb_ai
    app.include_router(bxb_ai.router)

Four ideas, each aimed at a manual step BXB pays people for today:
  /valuation   AI-drafted valuation report + analyst review + PDF   (the AED 8,500 valuation product)
  /feasibility count investors who pass the hard filters           (the AED 13,500 "min 3 matches" guarantee)
  /screen      listing screening and moderation queue              (admin approval, "License Verified")
  /verify      the grounding verifier under attack                 (trust in AI-written text)
  /scoreboard  every offline evaluation in one place

Security notes: uploaded PDFs are untrusted (size, magic bytes, temp file deleted, extraction errors reported without
details). Drafts live in memory for the demo and are readable only by their owner or a BXB admin. All data in the demo
is synthetic."""
from __future__ import annotations

import os
import tempfile
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlmodel import col, select

from app.api.deps import CurrentUser, SessionDep
from app.bxb import (
    feasibility as FZ,
    finance_extract as FE,
    listing_screen as LS,
    scoreboard as SB,
    valuation_report as VR,
    verifier_demo as VD,
)
from app.bxb.ai_schemas import FeasibilityIn, ListingDraftIn, ReviewIn, VerifyIn
from app.bxb.models import InvestorProfile, Listing, ListingStatus

router = APIRouter(prefix="/bxb/ai", tags=["bxb-ai"])
MAX_BYTES = 10 * 1024 * 1024


def _admin(user) -> None:
    if not user.is_superuser:
        raise HTTPException(403, "BXB admin only")


def _draft(draft_id: str, user) -> dict:
    d = VR.STORE.get(draft_id)
    if not d:
        raise HTTPException(404, "Draft not found (the demo store keeps recent drafts in memory)")
    if not user.is_superuser and d["owner"] != str(user.id):
        raise HTTPException(403, "Not allowed")
    return d


# --------------------------------------------------------------------------------------- valuation draft + review
@router.post("/valuation/draft")
def valuation_draft(
    file: UploadFile,
    user: CurrentUser,
    sector: Annotated[str, Query(min_length=1, max_length=80)],
    asking_price: Annotated[int | None, Query(ge=0)] = None,
) -> Any:
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "File larger than 10 MB")
    if not data.startswith(b"%PDF"):
        raise HTTPException(415, "Only PDF files are accepted")
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            out = FE.extract_pdf(path, file_name=os.path.basename(file.filename or "upload.pdf")[:200])
        except Exception as e:
            raise HTTPException(422, f"Could not read this PDF: {type(e).__name__}")
    finally:
        os.unlink(path)
    try:
        return VR.STORE.put(VR.build_draft(out, sector, asking_price, owner=str(user.id)))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/valuation/sample")
def valuation_sample(user: CurrentUser, kind: Annotated[str, Query(pattern="^(clean|fraud)$")] = "clean") -> Any:
    """Draft from a built-in SYNTHETIC statement. 'fraud' has a planted revenue/bank gap and an inflated gross profit."""
    return VR.STORE.put(VR.draft_sample(kind, owner=str(user.id)))


@router.get("/valuation/{draft_id}")
def valuation_get(draft_id: str, user: CurrentUser) -> Any:
    return _draft(draft_id, user)


@router.post("/valuation/{draft_id}/review")
def valuation_review(draft_id: str, body: ReviewIn, user: CurrentUser) -> Any:
    _admin(user)
    _draft(draft_id, user)
    if body.decision not in ("approve", "reject"):
        raise HTTPException(422, "decision must be 'approve' or 'reject'")
    try:
        return VR.STORE.review(draft_id, body.decision, body.reviewer, body.note)
    except KeyError:
        raise HTTPException(404, "Draft not found")
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/valuation/{draft_id}/pdf")
def valuation_pdf(draft_id: str, user: CurrentUser) -> Response:
    pdf = VR.render_pdf(_draft(draft_id, user))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="valuation-{draft_id[:8]}.pdf"'})


# ------------------------------------------------------------------------------------------------- feasibility
def _investors(session) -> list[dict]:
    return [p.model_dump() for p in session.exec(select(InvestorProfile))]


@router.get("/feasibility/listing/{listing_id}")
def feasibility_listing(
    listing_id: int,
    session: SessionDep,
    user: CurrentUser,
    guarantee: Annotated[int, Query(ge=1, le=20)] = 3,
    matches: Annotated[int, Query(ge=0, le=20)] = 0,
) -> Any:
    listing = session.get(Listing, listing_id)
    if not listing:
        raise HTTPException(404, "Listing not found")
    if not user.is_superuser and listing.owner_id != user.id:
        raise HTTPException(403, "Only the seller or a BXB admin can check this listing")
    if matches and not user.is_superuser:
        raise HTTPException(403, "Only a BXB admin can see investor names")
    return FZ.check(listing.model_dump(), _investors(session), guarantee, matches)


@router.post("/feasibility")
def feasibility_prospect(
    body: FeasibilityIn,
    session: SessionDep,
    user: CurrentUser,
    matches: Annotated[int, Query(ge=0, le=20)] = 0,
) -> Any:
    if matches and not user.is_superuser:
        raise HTTPException(403, "Only a BXB admin can see investor names")
    return FZ.check(body.model_dump(exclude={"guarantee"}), _investors(session), body.guarantee, matches)


# --------------------------------------------------------------------------------------------------- screening
@router.post("/screen/draft")
def screen_draft(body: ListingDraftIn, session: SessionDep, user: CurrentUser) -> Any:
    """Seller self-check before submitting a listing."""
    peers = session.exec(select(Listing.sector, Listing.annual_revenue).where(Listing.sector == body.sector).limit(5000)).all()
    stats = LS.sector_stats([{"sector": s, "annual_revenue": r} for s, r in peers])
    return LS.screen_listing(body.model_dump(), text=body.description, employees=body.employees,
                             image_sha256=body.image_sha256, stats=stats)


@router.get("/screen/queue")
def screen_queue(
    session: SessionDep,
    user: CurrentUser,
    min_status: Annotated[str, Query(pattern="^(review|hold)$")] = "review",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Any:
    """Moderation queue: drafts and active listings that the screen wants a person to look at, worst first."""
    _admin(user)
    rows = session.exec(select(Listing).where(col(Listing.status).in_([ListingStatus.draft, ListingStatus.active]))).all()
    listings = [r.model_dump() | {"status": r.status.value} for r in rows]
    results = LS.screen_all(listings)
    keep = {"hold"} if min_status == "hold" else {"review", "hold"}
    items = [
        {"listing_id": l["id"], "sector": l["sector"], "emirate": l["emirate"], "listing_status": l["status"],
         "asking_price": l["asking_price"], "score": r["score"], "screen_status": r["status"], "flags": r["flags"]}
        for l in listings if (r := results[l["id"]])["status"] in keep
    ]
    items.sort(key=lambda x: -x["score"])
    return {"screened": len(listings), "flagged": len(items), "items": items[:limit],
            "note": "Flags are prompts for a human check, not findings of fraud."}


@router.get("/screen/demo")
def screen_demo() -> Any:
    return {"cases": LS.run_demo(), "note": "Invented examples, not real listings."}


# ----------------------------------------------------------------------------------------------------- verifier
@router.get("/verify/demo")
def verify_demo() -> Any:
    return VD.run_attacks()


@router.post("/verify")
def verify_sentence(body: VerifyIn) -> Any:
    """Check any sentence against the demo fact bank (F1 to F5 in /verify/demo)."""
    return VD.check(body.sentence)


# --------------------------------------------------------------------------------------------------- scoreboard
@router.get("/scoreboard")
def scoreboard() -> Any:
    return SB.load() or {"status": "not_run", "hint": "POST /bxb/ai/scoreboard/refresh (admin) or run python -m app.bxb.scoreboard"}


@router.post("/scoreboard/refresh")
def scoreboard_refresh(user: CurrentUser) -> Any:
    """Recomputes every evaluation. Slow (tens of seconds); runs in the threadpool because the handler is sync."""
    _admin(user)
    return SB.refresh()
