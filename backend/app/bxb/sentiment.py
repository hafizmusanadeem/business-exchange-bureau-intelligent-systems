"""Module 2: Investor Sentiment. Pure functions (stdlib only), so every number is testable
without a database. Routes load rows from Postgres and call these.

DEFINITIONS (keep in sync with README):
  demand unit   = unique (investor, listing) pair with a QUALIFIED event (enquiry, meeting, offer)
                  inside the period. Views and saves never count.
  sector share  = demand units in sector / all demand units in the period, in percent.
  trend         = share change in percentage points between two periods. Called "increasing" or
                  "decreasing" only if a two-proportion z-test gives p < 0.05 AND the move is >= 1 pt;
                  otherwise "stable". Periods below MIN_UNITS are marked low-confidence.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import date
from math import erf, sqrt

MIN_UNITS = 30
BUDGET_BANDS = [(0, 1_000_000, "under AED 1M"), (1_000_000, 2_000_000, "AED 1M to 2M"),
                (2_000_000, 5_000_000, "AED 2M to 5M"), (5_000_000, 10**12, "over AED 5M")]


def quarter_of(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def quarter_bounds(q: str) -> tuple[date, date]:
    y, n = int(q[:4]), int(q[-1])
    s = date(y, 3 * (n - 1) + 1, 1)
    e = date(y + (n == 4), 1 if n == 4 else 3 * n + 1, 1)
    return s, e  # [s, e)


def demand_units(events: list[dict], start: date, end: date) -> set[tuple[int, int, str]]:
    return {(e["investor_id"], e["listing_id"], e["sector"]) for e in events
            if e["qualified"] and start <= e["occurred_on"] < end}


def sector_shares(events: list[dict], start: date, end: date) -> dict:
    units = demand_units(events, start, end)
    n = len(units)
    c = Counter(s for _, _, s in units)
    return {"n": n, "low_confidence": n < MIN_UNITS,
            "sectors": {s: {"units": k, "share_pct": round(100 * k / n, 1), "ci95_pct": wilson(k, n)} for s, k in c.items()} if n else {}}


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n; d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * (centre - half), 1), round(100 * (centre + half), 1)]


def two_prop_p(k1: int, n1: int, k2: int, n2: int) -> float:
    if min(n1, n2) == 0:
        return 1.0
    p = (k1 + k2) / (n1 + n2)
    se = sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = abs(k2 / n2 - k1 / n1) / se
    return 2 * (1 - 0.5 * (1 + erf(z / sqrt(2))))


def trend(events: list[dict], q_from: str, q_to: str) -> list[dict]:
    a, b = sector_shares(events, *quarter_bounds(q_from)), sector_shares(events, *quarter_bounds(q_to))
    rows = []
    for s in sorted(set(a["sectors"]) | set(b["sectors"])):
        ka = a["sectors"].get(s, {}).get("units", 0); kb = b["sectors"].get(s, {}).get("units", 0)
        sa = 100 * ka / a["n"] if a["n"] else 0.0; sb = 100 * kb / b["n"] if b["n"] else 0.0
        p = two_prop_p(ka, a["n"], kb, b["n"]); d = sb - sa
        label = ("increasing" if d > 0 else "decreasing") if (abs(d) >= 1 and p < 0.05) else "stable"
        rows.append({"sector": s, "from": q_from, "to": q_to, "share_from_pct": round(sa, 1), "share_to_pct": round(sb, 1),
                     "change_pts": round(d, 1), "p_value": round(p, 4), "trend": label,
                     "low_confidence": a["low_confidence"] or b["low_confidence"]})
    return sorted(rows, key=lambda r: -r["change_pts"])


def country_mix(events: list[dict], investors: dict[int, dict], start: date, end: date) -> list[dict]:
    inv = {i for i, _, _ in demand_units(events, start, end)}
    c = Counter(investors[i]["country"] for i in inv if i in investors)
    n = sum(c.values())
    return [{"country": k, "investors": v, "share_pct": round(100 * v / n, 1)} for k, v in c.most_common()] if n else []


def budget_band(budget_max: int) -> str:
    return next(label for lo, hi, label in BUDGET_BANDS if lo <= budget_max < hi)


def segments(events: list[dict], investors: dict[int, dict], start: date, end: date) -> dict:
    """Rule-based and explainable. An investor can sit in several segments."""
    units = demand_units(events, start, end)
    per_inv: dict[int, list] = defaultdict(list)
    for i, l, s in units:
        per_inv[i].append(s)
    out: dict[str, set] = defaultdict(set)
    for i, secs in per_inv.items():
        p = investors.get(i)
        if not p:
            continue
        top, cnt = Counter(secs).most_common(1)[0]
        if len(secs) >= 3 and cnt / len(secs) >= 0.6:
            out[f"{top} focused"].add(i)
        out[f"Budget: {budget_band(p['budget_max'])}"].add(i)
        if p["country"] != "UAE":
            out["International"].add(i)
        if len(secs) >= 4:
            out["Repeat enquirers (4+)"].add(i)
    return {k: len(v) for k, v in sorted(out.items(), key=lambda kv: -len(kv[1]))}


def band_shift(events: list[dict], investors: dict[int, dict], sector: str, q_from: str, q_to: str) -> list[dict]:
    """Where did a sector's growth come from, by investor budget band (unique investors)?"""
    def counts(q):
        s, e = quarter_bounds(q)
        inv = {i for i, _, sec in demand_units(events, s, e) if sec == sector and i in investors}
        return Counter(budget_band(investors[i]["budget_max"]) for i in inv)
    a, b = counts(q_from), counts(q_to)
    return [{"band": lbl, "from": a.get(lbl, 0), "to": b.get(lbl, 0), "delta": b.get(lbl, 0) - a.get(lbl, 0)}
            for _, _, lbl in BUDGET_BANDS]


def facts(events: list[dict], investors: dict[int, dict], q_from: str, q_to: str) -> list[dict]:
    """Structured, number-bearing facts. Module 6 (LLM reports) may only verbalise these."""
    rows = [r for r in trend(events, q_from, q_to) if r["trend"] != "stable"]
    out, seen = [], set()
    for r in rows[:3] + rows[-2:]:
        if r["sector"] in seen:
            continue
        seen.add(r["sector"])
        f = {"type": "sector_trend", **r}
        if r["trend"] == "increasing":
            top = max(band_shift(events, investors, r["sector"], q_from, q_to), key=lambda x: x["delta"])
            f["largest_growth_band"] = top["band"]; f["largest_growth_delta_investors"] = top["delta"]
        out.append(f)
    return out
