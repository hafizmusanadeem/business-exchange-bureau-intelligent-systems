"""Module 3a: Business Sale Trends and Demand vs Supply. Pure Python (stdlib).
ASKING PRICE IS NOT SALE PRICE: nothing here claims transaction values.
DEFINITIONS
  active at date D  = listed on or before D and not closed on or before D.
  days on market    = closed_on - listed_on for closed listings; age = D - listed_on for active ones.
  conversion rate   = listings (listed in the 90 days to D) that received a QUALIFIED enquiry / all such listings.
  supply share      = sector's active listings at quarter end / all active listings.
  demand share      = Module 2 sector share for the same quarter.
  gap               = demand - supply in points. Labelled only when |gap| >= 3 pts AND the 95% intervals
                      do not overlap; otherwise "balanced". A label is a prompt to investigate, not proof.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date, timedelta
from statistics import mean, median
try:
    from app.bxb import sentiment as S
except ImportError:  # flat import when running tests without the template
    import sentiment as S


def active_at(listings: list[dict], d: date) -> list[dict]:
    return [l for l in listings if l["listed_on"] <= d and (l["closed_on"] is None or l["closed_on"] > d)]


def _stats(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    return {"n": len(vals), "median": round(median(vals)), "mean": round(mean(vals)), "min": round(min(vals)), "max": round(max(vals))}


def market_stats(listings: list[dict], events: list[dict], as_of: date, sector: str | None = None) -> dict:
    pool = [l for l in listings if sector in (None, l["sector"])]
    act = active_at(pool, as_of)
    w0, w1 = as_of - timedelta(days=90), as_of
    prev0 = w0 - timedelta(days=90)
    new_now = [l for l in pool if w0 < l["listed_on"] <= w1]
    new_prev = [l for l in pool if prev0 < l["listed_on"] <= w0]
    closed12 = [l for l in pool if l["closed_on"] and as_of - timedelta(days=365) < l["closed_on"] <= as_of]
    qualified = {e["listing_id"] for e in events if e["qualified"] and e["occurred_on"] <= as_of}
    conv = sum(1 for l in new_now if l["id"] in qualified)
    return {
        "sector": sector or "All", "as_of": as_of.isoformat(), "active_listings": len(act),
        "asking_price_aed": _stats([l["asking_price"] for l in act]),
        "asking_to_ebitda_x": _ratio(act, "ebitda"), "asking_to_revenue_x": _ratio(act, "annual_revenue"),
        "median_age_active_days": int(median([(as_of - l["listed_on"]).days for l in act])) if act else None,
        "median_days_to_close": int(median([(l["closed_on"] - l["listed_on"]).days for l in closed12])) if closed12 else None,
        "closed_last_12m": {"sold": sum(l["status"] == "sold" for l in closed12), "expired": sum(l["status"] == "expired" for l in closed12)},
        "new_listings_90d": len(new_now), "new_listings_prev_90d": len(new_prev),
        "new_listings_change_pct": round(100 * (len(new_now) - len(new_prev)) / len(new_prev), 1) if new_prev else None,
        "conversion_rate_pct": round(100 * conv / len(new_now), 1) if new_now else None, "conversion_n": len(new_now),
        "note": "Asking prices only. Not transaction values.",
    }


def _ratio(rows: list[dict], key: str) -> dict:
    r = [l["asking_price"] / l[key] for l in rows if l[key] > 0]
    return {"n": len(r), "median": round(median(r), 2)} if r else {"n": 0}


def geography(listings: list[dict], as_of: date) -> list[dict]:
    act = active_at(listings, as_of); c = Counter(l["emirate"] for l in act); n = len(act)
    return [{"emirate": k, "active_listings": v, "share_pct": round(100 * v / n, 1)} for k, v in c.most_common()] if n else []


def monthly_series(listings: list[dict], sector: str | None, metric: str = "new_listings") -> list[tuple[str, float]]:
    by: dict[str, list] = defaultdict(list)
    for l in listings:
        if sector in (None, l["sector"]):
            by[l["listed_on"].strftime("%Y-%m")].append(l)
    if not by:
        return []
    keys = sorted(by); y, m = map(int, keys[0].split("-")); ye, me = map(int, keys[-1].split("-"))
    out = []
    while (y, m) <= (ye, me):  # fill gaps with zero (counts) or carry-forward (prices)
        k = f"{y}-{m:02d}"; rows = by.get(k, [])
        v = len(rows) if metric == "new_listings" else (median([r["asking_price"] for r in rows]) if rows else (out[-1][1] if out else 0))
        out.append((k, float(v))); m += 1
        if m == 13: y, m = y + 1, 1
    return out


def demand_vs_supply(listings: list[dict], events: list[dict], quarter: str, gap_pts: float = 3.0) -> list[dict]:
    start, end = S.quarter_bounds(quarter)
    last_day = end - timedelta(days=1)
    dem = S.sector_shares(events, start, end)
    act = active_at(listings, last_day); sup_n = len(act); sup_c = Counter(l["sector"] for l in act)
    rows = []
    for s in sorted(set(dem["sectors"]) | set(sup_c)):
        d = dem["sectors"].get(s, {"units": 0, "share_pct": 0.0, "ci95_pct": [0.0, 0.0]})
        sk = sup_c.get(s, 0); sh = round(100 * sk / sup_n, 1) if sup_n else 0.0
        sci = S.wilson(sk, sup_n); gap = round(d["share_pct"] - sh, 1)
        separated = d["ci95_pct"][0] > sci[1] or sci[0] > d["ci95_pct"][1]
        label = "balanced"
        if abs(gap) >= gap_pts and separated:
            label = "under-supplied" if gap > 0 else "over-supplied"
        rows.append({"sector": s, "demand_share_pct": d["share_pct"], "supply_share_pct": sh, "gap_pts": gap, "label": label,
                     "enquiry_units_per_active_listing": round(d["units"] / sk, 2) if sk else None,
                     "low_confidence": dem["low_confidence"] or sup_n < S.MIN_UNITS,
                     "caveat": "Prompt to investigate: check investor budgets and listing quality before concluding."})
    return sorted(rows, key=lambda r: -r["gap_pts"])
