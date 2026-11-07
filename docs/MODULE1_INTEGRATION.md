# Running BXB Pulse from a clean checkout

This repo is standalone: FastAPI + SQLModel + PostgreSQL, and a static frontend in `frontend/`
that FastAPI serves. It does not need the full-stack-fastapi-template.

## 1. Install

```bash
uv sync            # or: pip install -e .   (Python 3.13)
```

## 2. Database

Create an empty PostgreSQL database, then put its URL in `backend/.env`:

```
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@localhost:5432/bxb
```

```bash
cd backend
alembic upgrade head        # creates user, profile, listing, investorprofile, investorevent, financialfact
python -m app.bxb.seed      # safe to re-run; local only (ENVIRONMENT must be "local", the default)
```

The seed loads 36 months of SYNTHETIC listings, 500 investors and about 20,000 events, plus:

- demo users (password `demopass123`) `seller@bxb.demo`, `investor@bxb.demo`, `admin@bxb.demo`;
- `dev@bxb.local`, the user that `app/api/deps.py` hands to every request. Its row must exist,
  or "Register interest" in the deal room fails on a foreign key;
- five INVENTED draft listings with deliberately implausible numbers. Drafts never appear in the
  marketplace, sentiment or reports, but the AI Lab "Screen database listings" queue flags them.

There is no login yet: `deps.py` treats every request as the dev superuser. Replace it before
anything is deployed.

If your database was created some other way (for example `SQLModel.metadata.create_all`), do not
run `alembic upgrade head` on it. Run `alembic stamp head` instead, then the seed.

## 3. Run

```bash
cd backend
uvicorn app.main:app --reload
```

Open <http://localhost:8000/> (marketplace), `/valuation.html` and `/ai-lab.html`.
Valuation drafts are kept in memory, so restarting the server clears them.

## 4. Tests and evaluations

```bash
PYTHONPATH=backend python -m pytest tests/ -q
PYTHONPATH=backend python -m app.bxb.scoreboard     # rewrites backend/scoreboard.json
```

The tests need no database. Fonts and Tailwind load from CDNs, so the pages need internet.
