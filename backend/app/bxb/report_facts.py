"""Module 6a: the FACT BANK. Every number a report may contain is computed here by Modules 2 and 3.
A fact is {id, type, entity, direction, values{name: number}, labels[str], periods[str]}.
Text may only cite facts; the verifier (grounding.py) checks the text against them."""
from __future__ import annotations
from datetime import date
try:
    from app.bxb import forecast as F, sentiment as S, trends as T
except ImportError:
    import forecast as F, sentiment as S, trends as T


def collect_facts(events, listings, investors: dict, q_from: str, q_to: str, as_of: date, horizon: int = 6) -> list[dict]:
    facts: list[dict] = []
    def add(type_, entity=None, direction=None, values=None, labels=None, periods=None):
        facts.append({"id": f"F{len(facts) + 1}", "type": type_, "entity": entity, "direction": direction,
                      "values": {k: v for k, v in (values or {}).items() if v is not None}, "labels": labels or [], "periods": periods or []})
    a, b = S.sector_shares(events, *S.quarter_bounds(q_from)), S.sector_shares(events, *S.quarter_bounds(q_to))
    add("coverage", values={"n_from": a["n"], "n_to": b["n"], "min_units": S.MIN_UNITS, "active_listings": len(T.active_at(listings, as_of))},
        direction="low_confidence" if (a["low_confidence"] or b["low_confidence"]) else "ok", periods=[q_from, q_to])
    tr = S.trend(events, q_from, q_to); moved = [r for r in tr if r["trend"] != "stable"]
    for r in moved:
        add("sector_trend", r["sector"], r["trend"], {"share_from_pct": r["share_from_pct"], "share_to_pct": r["share_to_pct"], "change_pts": abs(r["change_pts"]), "p_value": round(r["p_value"], 3)}, periods=[q_from, q_to])
        if r["trend"] == "increasing":
            top = max(S.band_shift(events, investors, r["sector"], q_from, q_to), key=lambda x: x["delta"])
            if top["delta"] > 0:
                add("growth_band", r["sector"], "increasing", {"delta_investors": top["delta"]}, labels=[top["band"]], periods=[q_from, q_to])
    add("stable_summary", direction="stable", values={"n_stable": sum(r["trend"] == "stable" for r in tr)}, periods=[q_from, q_to])
    for r in T.demand_vs_supply(listings, events, q_to):
        if r["label"] != "balanced":
            add("demand_supply", r["sector"], r["label"], {"demand_share_pct": r["demand_share_pct"], "supply_share_pct": r["supply_share_pct"], "gap_pts": abs(r["gap_pts"])}, periods=[q_to])
    m = T.market_stats(listings, events, as_of)
    chg = m["new_listings_change_pct"]
    add("market", direction=None if chg is None else "increasing" if chg >= 5 else "decreasing" if chg <= -5 else "stable",
        values={"active_listings": m["active_listings"], "median_asking_aed": m["asking_price_aed"].get("median"), "median_days_to_close": m["median_days_to_close"],
                "conversion_rate_pct": m["conversion_rate_pct"], "conversion_n": m["conversion_n"], "window_days": 90, "lookback_months": 12, "new_listings_change_pct": abs(chg) if chg is not None else None})
    fc = F.forecast([v for _, v in T.monthly_series(listings, None)], horizon)
    if fc["status"] == "ok":
        add("forecast", direction="beats_baseline" if fc["beats_baseline"] else "baseline_used", labels=[fc["model"].replace("_", " ")],
            values={"f_min": int(min(fc["forecast"])), "f_max": round(max(fc["forecast"])), "horizon": horizon, "mae_model": fc["backtest"][fc["model"]]["mae"], "mae_naive": fc["backtest"]["naive"]["mae"]})
    else:
        add("forecast_unavailable", direction="insufficient_history")
    return facts
