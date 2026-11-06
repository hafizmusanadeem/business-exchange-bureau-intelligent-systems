# BXB Pulse – Modules 1–6 Integration Guide

Drop-in layer for the official
[full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template).

## Files

```
backend/app/bxb/
  models.py, synthetic.py, seed.py
  sentiment.py
  trends.py, forecast.py
  matching.py, metrics.py, eval_matching.py
  finance_extract.py, finance_validate.py, valuation.py, finance_synth.py
  report_facts.py, grounding.py, report_writer.py, eval_grounding.py

backend/app/api/routes/
  bxb.py, bxb_sentiment.py, bxb_trends.py, bxb_matching.py,
  bxb_financials.py, bxb_reports.py

backend/app/alembic/versions/
  2026_11_06_0001_bxb_foundation.py   # includes FinancialFact

tests/
  test_synthetic.py, test_sentiment.py, test_trends.py,
  test_matching.py, test_finance.py, test_grounding.py
```

## Integration steps

1. Copy into the template:
   ```bash
   cp -r backend/app/bxb               <template>/backend/app/
   cp    backend/app/api/routes/bxb*.py <template>/backend/app/api/routes/
   cp    backend/app/alembic/versions/2026_11_06_0001_bxb_foundation.py \
         <template>/backend/app/alembic/versions/
   ```

2. Register models (bottom of `app/models.py`):
   ```python
   from app.bxb.models import *  # noqa: F401,F403
   ```

3. Register routers (`app/api/main.py`):
   ```python
   from app.api.routes import (
       bxb, bxb_sentiment, bxb_trends, bxb_matching, bxb_financials, bxb_reports
   )
   for r in (bxb, bxb_sentiment, bxb_trends, bxb_matching, bxb_financials, bxb_reports):
       api_router.include_router(r.router)
   ```

4. Dependencies in `backend/pyproject.toml`:
   ```
   scikit-learn
   numpy
   joblib
   pdfplumber
   ```

5. Migration + seed:
   ```bash
   cd backend
   # set down_revision in the migration to the current alembic head
   alembic upgrade head
   python -m app.bxb.seed
   ```

## Demo credentials (password = `demopass123`)

| Email              | Role     |
|--------------------|----------|
| seller@bxb.demo    | seller   |
| investor@bxb.demo  | investor |
| admin@bxb.demo     | admin    |

## Key endpoints (Modules 5–6)

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `POST /bxb/financials/listings/{id}/upload` | Owner / admin | Upload financial PDF (10 MB max) |
| `GET /bxb/financials/listings/{id}/summary` | Owner / admin | Facts, validation flags, valuation range |
| `GET /bxb/reports/market?q_from=&q_to=` | Authenticated | Grounded market report (template or LLM) |

## Offline evaluation

```bash
PYTHONPATH=backend python -m app.bxb.eval_matching
PYTHONPATH=backend python -m app.bxb.finance_synth
PYTHONPATH=backend python -m app.bxb.eval_grounding
```

## Unit tests

```bash
PYTHONPATH=backend python -m pytest tests/ -q
```

Expect ~55 tests when pdfplumber is installed.
