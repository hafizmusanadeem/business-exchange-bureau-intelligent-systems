from fastapi import FastAPI

from app.api.routes import (
    bxb,
    bxb_financials,
    bxb_matching,
    bxb_reports,
    bxb_sentiment,
    bxb_trends,
)

app = FastAPI(title="BXB Pulse")

for _module in (
    bxb,
    bxb_sentiment,
    bxb_trends,
    bxb_matching,
    bxb_financials,
    bxb_reports,
):
    app.include_router(_module.router)


@app.get("/health")
def health():
    return {"status": "ok"}
