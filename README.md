# BXB Pulse – Module 1: Foundation (MVP)

Clean, template-ready implementation of Step 1 of the BXB Pulse development plan.

## What is included

- **Roles** – seller / investor / admin (`Profile` table linked to the template `User`)
- **Schema** – `Listing`, `InvestorProfile`, `InvestorEvent` (richer than a simple Enquiry)
- **Qualified interest** – `EventKind` + `QUALIFIED` set (views are never counted as demand)
- **Synthetic generator** – 36 months of history with planted demand/supply signals
- **Seed script** – loads the synthetic data + three demo users with known passwords
- **API routes** – list / create listings, change status, upsert investor profile, record events
- **Alembic migration stub** – ready to be chained onto the template’s current head
- **Unit tests** – pure stdlib tests for the generator (determinism, integrity, planted trends)

## Quick start

See [`docs/MODULE1_INTEGRATION.md`](docs/MODULE1_INTEGRATION.md) for the exact copy-paste steps into the official FastAPI full-stack template.

## Design decisions (aligned with the plan)

| Decision | Rationale |
|----------|-----------|
| `InvestorEvent` instead of a single `Enquiry` table | Supports the full sentiment definition (save / enquiry / meeting / offer) while still excluding page views |
| Explicit primary keys in the seed | Keeps synthetic IDs stable so later modules can refer to the same records |
| Demo users with fixed emails | Lets you exercise the authenticated endpoints immediately without a UI |
| No production hardening | MVP priority is speed; Docker / CI / rate-limiting stay with the template |

## Next modules

Once this is integrated you can start Module 2 (Investor Sentiment metrics) against the same tables and synthetic events.
