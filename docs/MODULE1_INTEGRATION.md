# BXB Pulse – Modules 1 & 2 Integration Guide

Drop-in layer for the official
[full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template).

## Files provided

```
backend/app/bxb/
  __init__.py
  models.py              # Profile, Listing, InvestorProfile, InvestorEvent
  synthetic.py           # 36-month synthetic data generator (stdlib only)
  seed.py                # loads synthetic data + 3 demo users
  sentiment.py           # Module 2 pure functions (shares, trends, segments, facts)

backend/app/api/routes/
  bxb.py                 # /bxb/* foundation endpoints
  bxb_sentiment.py       # /bxb/sentiment/* endpoints

backend/app/alembic/versions/
  2026_11_06_0001_bxb_foundation.py

tests/
  test_synthetic.py
  test_sentiment.py
```

## Integration steps

1. **Copy the folders** into your template checkout:
   ```bash
   cp -r backend/app/bxb               <template>/backend/app/
   cp    backend/app/api/routes/bxb.py           <template>/backend/app/api/routes/
   cp    backend/app/api/routes/bxb_sentiment.py <template>/backend/app/api/routes/
   cp    backend/app/alembic/versions/2026_11_06_0001_bxb_foundation.py \
         <template>/backend/app/alembic/versions/
   ```

2. **Make Alembic see the new models** – add one line to `backend/app/models.py`:
   ```python
   # at the bottom of app/models.py
   from app.bxb.models import *  # noqa: F401,F403  # ensure tables are registered
   ```

3. **Register both routers** – in `backend/app/api/main.py`:
   ```python
   from app.api.routes import bxb, bxb_sentiment
   api_router.include_router(bxb.router)
   api_router.include_router(bxb_sentiment.router)
   ```

4. **Fix the migration’s `down_revision`**:
   ```bash
   cd backend
   alembic heads          # note the current head
   # edit 2026_11_06_0001_bxb_foundation.py → set down_revision = "<that id>"
   alembic upgrade head
   ```

5. **Seed the data**:
   ```bash
   python -m app.bxb.seed
   ```

## Demo credentials (all passwords = `demopass123`)

| Email              | Role     | Purpose                          |
|--------------------|----------|----------------------------------|
| seller@bxb.demo    | seller   | owns every 7th listing           |
| investor@bxb.demo  | investor | linked to InvestorProfile id=1   |
| admin@bxb.demo     | admin    | is_superuser = True              |

## Module 2 endpoints (`/bxb/sentiment`)

| Endpoint | Query params | Purpose |
|----------|--------------|---------|
| `GET /sectors` | `quarter=2026-Q2` | Sector shares of qualified demand + Wilson 95% CIs |
| `GET /trend` | `q_from=2025-Q2&q_to=2026-Q2` | Share change with two-proportion z-test labels |
| `GET /countries` | `quarter=2026-Q2` | Country mix of active investors |
| `GET /segments` | `quarter=2026-Q2` | Rule-based investor segments |
| `GET /facts` | `q_from=…&q_to=…` | Structured number-bearing facts for Module 6 |

### Definitions (kept in code + README)

- **Demand unit** = unique `(investor, listing)` pair with a qualified event (enquiry / meeting / offer) inside the period. Views and saves never count.
- **Sector share** = units in sector / all units, in percent.
- **Trend** = “increasing” / “decreasing” only when a two-proportion z-test gives p < 0.05 **and** the move is ≥ 1 percentage point; otherwise “stable”.
- Quarters with < 30 units are flagged `low_confidence`.
- `facts()` returns the structured statements that the Grounded AI reports module may verbalise.

## Running the unit tests (no DB needed)

```bash
cd <this-package>
python -m pytest tests/ -q
```

## Notes for later modules

- Asking price is stored and exposed; never present it as a realised sale price.
- All synthetic data is labelled; re-point the same models at real BXB tables when ready.
- Module 2 is pure functions over the event stream – the same code works offline or against Postgres.
