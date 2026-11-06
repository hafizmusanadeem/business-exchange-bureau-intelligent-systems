# BXB Pulse – Module 1 (Foundation) Integration Guide

This package is designed to drop into the official
[full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template).

## Files provided

```
backend/app/bxb/
  __init__.py
  models.py          # Profile, Listing, InvestorProfile, InvestorEvent
  synthetic.py       # 36-month synthetic data generator (stdlib only)
  seed.py            # loads synthetic data + 3 demo users

backend/app/api/routes/
  bxb.py             # /bxb/* endpoints

backend/app/alembic/versions/
  2026_11_06_0001_bxb_foundation.py   # migration stub

tests/
  test_synthetic.py
```

## Integration steps (5 minutes)

1. **Copy the folders** into your template checkout:
   ```bash
   cp -r backend/app/bxb          <template>/backend/app/
   cp    backend/app/api/routes/bxb.py  <template>/backend/app/api/routes/
   cp    backend/app/alembic/versions/2026_11_06_0001_bxb_foundation.py \
         <template>/backend/app/alembic/versions/
   ```

2. **Make Alembic see the new models** – add one line to `backend/app/models.py`:
   ```python
   # at the bottom of app/models.py
   from app.bxb.models import *  # noqa: F401,F403  # ensure tables are registered
   ```

3. **Register the router** – in `backend/app/api/main.py`:
   ```python
   from app.api.routes import bxb
   api_router.include_router(bxb.router)
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

## What the seed produces

- ~3–4 k listings across 7 sectors, 36 months
- 500 investor profiles
- several thousand InvestorEvents (views + qualified interest)
- Planted trends ready for Module 2 (Healthcare demand ↑, Retail ↓, F&B seasonality, IT oversupply)

## Running the unit tests (no DB needed)

```bash
cd <this-package>
python -m pytest tests/test_synthetic.py -q
```

## Notes for later modules

- `QUALIFIED = {enquiry, meeting, offer}` – page views are never counted as demand.
- Asking price is stored and exposed; never present it as a realised sale price.
- All synthetic data is labelled; re-point the same models at real BXB tables when ready.
