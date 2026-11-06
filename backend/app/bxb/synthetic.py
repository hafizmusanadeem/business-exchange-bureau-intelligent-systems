"""Synthetic BXB-style data: 36 months of listings, investors and enquiries.
Pure standard library so it can be tested without a database. ALL DATA IS SYNTHETIC.

Planted signals (so later modules have something real to detect):
  - Healthcare investor demand rises steadily; F&B has Q4 seasonality; Retail declines.
  - Technology has many listings but weak demand (oversupply).
"""
from __future__ import annotations

import random
from datetime import date, timedelta

SECTORS = {  # name: (listing weight, demand weight, median asking AED, demand trend per month)
    "Food & Beverage": (180, 18, 1_400_000, +0.006),
    "Healthcare": (42, 8, 3_200_000, +0.03),
    "Beauty": (88, 12, 650_000, 0.0),
    "Information Technology": (140, 8, 1_900_000, -0.006),
    "Commercial Services": (96, 9, 1_100_000, -0.002),
    "Retail": (120, 10, 800_000, -0.015),
    "Logistics": (38, 5, 2_600_000, +0.01),
}
EMIRATES = {"Dubai": 0.5, "Abu Dhabi": 0.2, "Sharjah": 0.15, "Ajman": 0.05, "Other": 0.1}
COUNTRIES = {
    "China": 27, "United States": 21, "Singapore": 9, "Canada": 7, "India": 7,
    "United Kingdom": 4, "Pakistan": 3, "UAE": 22,
}
RISK = ["low", "medium", "high"]


def _pick(rng: random.Random, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def month_start(end: date, months_back: int) -> date:
    y, m = end.year, end.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def generate(
    seed: int = 42,
    months: int = 36,
    n_investors: int = 500,
    end: date = date(2026, 6, 30),
) -> dict:
    rng = random.Random(seed)

    # --- listings: volume follows sector weight, mild growth, summer dip
    listings, lid = [], 0
    for k in range(months):
        start = month_start(end, months - 1 - k)
        for sector, (w, _, med, _) in SECTORS.items():
            n = max(
                0,
                round(
                    rng.gauss(
                        w / 12 * (1 + 0.01 * k) * (0.85 if start.month in (7, 8) else 1),
                        1.2,
                    )
                ),
            )
            for _ in range(n):
                lid += 1
                ask = max(100_000, rng.lognormvariate(0, 0.6) * med)
                margin = rng.uniform(0.12, 0.30)
                rev = ask / rng.uniform(0.5, 1.2)
                listed = start + timedelta(days=rng.randint(0, 27))
                days = max(
                    7,
                    int(rng.gauss(95 if sector == "Information Technology" else 75, 30)),
                )
                status = rng.choices(
                    ["sold", "expired", "active"], [0.12, 0.28, 0.60]
                )[0]
                listings.append(
                    dict(
                        id=lid,
                        sector=sector,
                        emirate=_pick(rng, EMIRATES),
                        years_operating=rng.randint(1, 20),
                        annual_revenue=round(rev),
                        ebitda=round(rev * margin),
                        asking_price=round(ask, -3),
                        ownership_pct=rng.choice([100, 100, 100, 70, 51]),
                        listed_on=listed,
                        status=status,
                        closed_on=(listed + timedelta(days=days))
                        if status != "active"
                        else None,
                    )
                )

    # --- investors with declared preferences
    investors = []
    for i in range(1, n_investors + 1):
        prim = rng.choices(
            list(SECTORS), weights=[v[1] for v in SECTORS.values()]
        )[0]
        sec = rng.sample(
            [s for s in SECTORS if s != prim], rng.choice([0, 1, 1, 2])
        )
        lo = rng.choice([250_000, 500_000, 1_000_000, 2_000_000, 4_000_000])
        investors.append(
            dict(
                id=i,
                name=f"Investor {i:03d}",
                country=_pick(rng, COUNTRIES),
                budget_min=lo,
                budget_max=lo * rng.choice([2, 3, 4]),
                sectors=[prim] + sec,
                emirates=rng.sample(list(EMIRATES), rng.choice([1, 2, 3])),
                min_ebitda=rng.choice([0, 100_000, 250_000, 500_000]),
                risk_appetite=rng.choice(RISK),
                joined_on=month_start(
                    end,
                    rng.randint(months - 6, months - 1)
                    if rng.random() < 0.8
                    else rng.randint(0, months - 1),
                ),
            )
        )

    # --- enquiries: investor -> listing, sector chosen by drifting demand
    by_sector: dict = {}
    for l in listings:
        by_sector.setdefault(l["sector"], []).append(l)

    enquiries, eid = [], 0
    for k in range(months):
        start = month_start(end, months - 1 - k)
        for inv in investors:
            if inv["joined_on"] > start or rng.random() > 0.30:
                continue
            w = {
                s: max(
                    0.1,
                    SECTORS[s][1]
                    * (1 + SECTORS[s][3] * k * 12 / 12)
                    * (1.25 if s == "Food & Beverage" and start.month >= 10 else 1)
                    * (3 if s in inv["sectors"] else 0.4),
                )
                for s in SECTORS
            }
            s = _pick(rng, w)
            pool = [
                l
                for l in by_sector.get(s, [])
                if l["listed_on"] <= start + timedelta(days=28)
            ]
            if not pool:
                continue
            l = rng.choice(pool)
            eid += 1
            fit = inv["budget_min"] <= l["asking_price"] <= inv["budget_max"]
            kind = rng.choices(
                ["view", "save", "enquiry", "meeting", "offer"],
                [50, 20, 20 if fit else 8, 6 if fit else 1, 3 if fit else 0.2],
            )[0]
            enquiries.append(
                dict(
                    id=eid,
                    investor_id=inv["id"],
                    listing_id=l["id"],
                    sector=s,
                    kind=kind,
                    qualified=kind in ("enquiry", "meeting", "offer"),
                    occurred_on=start + timedelta(days=rng.randint(0, 27)),
                )
            )

    return dict(listings=listings, investors=investors, events=enquiries)


if __name__ == "__main__":
    d = generate()
    print({k: len(v) for k, v in d.items()})
