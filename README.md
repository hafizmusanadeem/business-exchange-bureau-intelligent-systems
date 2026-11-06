# BXB Pulse – Modules 1 & 2 (MVP)

Clean, template-ready implementation of Steps 1–2 of the BXB Pulse development plan.

## What is included

### Module 1 – Foundation
- **Roles** – seller / investor / admin (`Profile` table linked to the template `User`)
- **Schema** – `Listing`, `InvestorProfile`, `InvestorEvent`
- **Qualified interest** – `EventKind` + `QUALIFIED` set (views are never counted as demand)
- **Synthetic generator** – 36 months of history with planted demand/supply signals
- **Seed script** – synthetic data + three demo users with known passwords
- **API routes** – list / create listings, change status, upsert investor profile, record events
- **Alembic migration stub**

### Module 2 – Investor Sentiment
- Pure functions (`sentiment.py`) for sector shares, trends, country mix, segments and facts
- Wilson 95% confidence intervals and two-proportion z-test for trend labels
- API under `/bxb/sentiment` (sectors, trend, countries, segments, facts)
- Unit tests that prove the planted Healthcare rise is detected

## Quick start

See [`docs/MODULE1_INTEGRATION.md`](docs/MODULE1_INTEGRATION.md) for the exact copy-paste steps into the official FastAPI full-stack template.

## Design decisions (aligned with the plan)

| Decision | Rationale |
|----------|-----------|
| `InvestorEvent` instead of a single `Enquiry` table | Supports the full sentiment definition (save / enquiry / meeting / offer) while still excluding page views |
| Demand unit = unique (investor, listing) | Prevents one active investor from dominating a sector’s share |
| Trend requires p < 0.05 **and** ≥ 1 pt move | Avoids calling noise “increasing” |
| Explicit primary keys in the seed | Keeps synthetic IDs stable so later modules can refer to the same records |
| Demo users with fixed emails | Lets you exercise the authenticated endpoints immediately |
| No production hardening | MVP priority is speed; Docker / CI / rate-limiting stay with the template |

## Next modules

Once this is integrated you can start Module 3 (Business Sale Trends & Demand vs Supply) against the same tables and synthetic events.
