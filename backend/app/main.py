from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    bxb,
    bxb_ai,
    bxb_financials,
    bxb_matching,
    bxb_public,
    bxb_reports,
    bxb_sentiment,
    bxb_trends,
)

app = FastAPI(title="BXB Pulse")

# API routers first: the static mount at "/" below is a catch-all.
app.include_router(bxb.router)
app.include_router(bxb_public.router)
app.include_router(bxb_sentiment.router)
app.include_router(bxb_trends.router)
app.include_router(bxb_matching.router)
app.include_router(bxb_financials.router)
app.include_router(bxb_reports.router)
app.include_router(bxb_ai.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Frontend lives at <repo>/frontend (backend/app/main.py -> parents[2] is the repo root).
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
