"""BXB Financial Intelligence routes (Module 5).

Register in app/api/main.py:

    from app.api.routes import bxb_financials
    api_router.include_router(bxb_financials.router)

Add `pdfplumber` to backend/pyproject.toml (and `python-multipart`).
Security notes: PDFs are untrusted. Size and page limits apply, uploads go to a
temp file that is deleted, the client file name is stored only as a label.
Run extraction in a worker with a timeout before real BXB documents are accepted."""
import os, tempfile
from typing import Any
from fastapi import APIRouter, HTTPException, UploadFile
from sqlmodel import delete, select
from app.api.deps import CurrentUser, SessionDep
from app.bxb import finance_extract as FE, finance_validate as FV, valuation as V
from app.bxb.models import FinancialFact, Listing

router = APIRouter(prefix="/bxb/financials", tags=["bxb-financials"])
MAX_BYTES = 10 * 1024 * 1024


def _own(session, user, listing_id) -> Listing:
    l = session.get(Listing, listing_id)
    if not l: raise HTTPException(404, "Listing not found")
    if not user.is_superuser and l.owner_id != user.id: raise HTTPException(403, "Not allowed")
    return l


def _facts(session, listing_id) -> list[dict]:
    rows = session.exec(select(FinancialFact).where(FinancialFact.listing_id == listing_id)).all()
    return [{**r.model_dump(), "file": r.file_name, "table": r.table_index} for r in rows]


@router.post("/listings/{listing_id}/upload")
async def upload(listing_id: int, file: UploadFile, session: SessionDep, user: CurrentUser) -> Any:
    _own(session, user, listing_id)
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES: raise HTTPException(413, "File larger than 10 MB")
    if not data.startswith(b"%PDF"): raise HTTPException(415, "Only PDF files are accepted")
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as fh: fh.write(data)
        try: out = FE.extract_pdf(path, file_name=os.path.basename(file.filename or "upload.pdf")[:200])
        except Exception as e: raise HTTPException(422, f"Could not read this PDF: {type(e).__name__}")
    finally:
        os.unlink(path)
    for f in out["facts"]:
        session.add(FinancialFact(listing_id=listing_id, metric=f["metric"], period=f["period"], value=f["value"], raw=f["raw"][:80], label=f["label"][:160],
                                  file_name=f["file"], page=f["page"], table_index=f["table"], row=f["row"], col=f["col"], bbox=f["bbox"],
                                  scale=f["scale"], confidence=f["confidence"], mapped_by=f["mapped_by"]))
    session.commit()
    return {"stored_facts": len(out["facts"]), "unmapped_labels": out["unmapped"], "warnings": out["warnings"]}


@router.get("/listings/{listing_id}/summary")
def summary(listing_id: int, session: SessionDep, user: CurrentUser) -> Any:
    l = _own(session, user, listing_id)
    facts = _facts(session, listing_id)
    if not facts: raise HTTPException(404, "No financial documents uploaded yet")
    idx = FV.index(facts); flags = FV.validate(facts); q = FV.quality_score(flags)
    periods = sorted({f["period"] for f in facts}); latest = next((p for p in reversed(periods) if FV.derive_ebitda(idx, p)), None)
    e = FV.derive_ebitda(idx, latest) if latest else None
    hist = {p: FV.derive_ebitda(idx, p)["value"] for p in periods if FV.derive_ebitda(idx, p)}
    debt, cash = FV.best(idx, "debt", latest) if latest else None, FV.best(idx, "cash", latest) if latest else None
    net_debt = (debt["value"] if debt else 0) - (cash["value"] if cash else 0) if (debt or cash) else None
    return {"listing_id": listing_id, "latest_period": latest, "ebitda": e, "data_quality_score": q, "flags": flags,
            "valuation": V.valuate(e["value"] if e else None, l.sector, hist, l.asking_price, net_debt, q, flags, bool(e and e["approximate"])),
            "facts": facts}
