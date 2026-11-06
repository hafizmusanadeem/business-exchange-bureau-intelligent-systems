from fastapi import FastAPI

from app.api.routes import bxb, bxb_sentiment

app = FastAPI(title="BXB Pulse")

app.include_router(bxb.router)
app.include_router(bxb_sentiment.router)


@app.get("/health")
def health():
    return {"status": "ok"}
