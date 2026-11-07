"""Module 8c: sale-service feasibility. "Can we honestly promise this seller N investor matches?"

BXB sells a Business Sale Service with a guaranteed minimum number of investor matches. Before the package is sold
(and again before the guarantee is promised), count the investors who pass Module 4's HARD FILTERS for the listing.
Counts only by default: investor names are returned only when explicitly requested (admin).

Status for a guarantee of g matches and n passing investors:
    n >= 2g  safe        n >= g  tight        1 <= n < g  at_risk        n == 0  not_viable
A what-if table shows how the count changes if the asking price is cut. A price cut can also push the price BELOW
some investors' budgets, so the table reports the true count each time and suggests the smallest cut that works.

Pure Python. Reuses matching.hard_filter, so the answer can never disagree with the ranker."""
from __future__ import annotations

from collections import Counter

try:
    from app.bxb import matching as M
except ImportError:
    import matching as M

PRICE_CUTS = (10, 20, 30)


def _status(n: int, g: int) -> str:
    return "safe" if n >= 2 * g else "tight" if n >= g else "at_risk" if n >= 1 else "not_viable"


def _message(n: int, g: int, status: str) -> str:
    return {
        "safe": f"{n} investors pass the hard filters, comfortably above the guarantee of {g}.",
        "tight": f"{n} investors pass the hard filters, enough for the guarantee of {g} but with little margin.",
        "at_risk": f"Only {n} investor(s) pass the hard filters, fewer than the guarantee of {g}. Adjust the listing or do not promise {g}.",
        "not_viable": "No investor passes the hard filters. Do not sell a guaranteed-match package for this listing as it stands.",
    }[status]


def count_passing(listing: dict, investors: list[dict]) -> int:
    return sum(not M.hard_filter(listing, i) for i in investors)


def check(listing: dict, investors: list[dict], guarantee: int = 3, top_k: int = 0, scorer=None) -> dict:
    """listing needs: sector, asking_price, ebitda, annual_revenue, emirate, ownership_pct, years_operating.
    investors need the fields used by matching.hard_filter. top_k > 0 adds ranked investor names (admin only)."""
    if guarantee < 1:
        raise ValueError("guarantee must be at least 1")
    listing = {"id": 0, **listing}
    reasons: Counter = Counter(); passing = []
    for inv in investors:
        why = M.hard_filter(listing, inv)
        (reasons.update(why) if why else passing.append(inv))
    n = len(passing); status = _status(n, guarantee)
    what_if = []
    for cut in PRICE_CUTS:
        price = round(listing["asking_price"] * (1 - cut / 100))
        what_if.append({"price_cut_pct": cut, "asking_price": price, "investors_passing": count_passing({**listing, "asking_price": price}, investors)})
    suggestion = None
    if n < guarantee:
        ok = [w for w in what_if if w["investors_passing"] >= guarantee]
        suggestion = (f"A price cut of {ok[0]['price_cut_pct']}% would bring {ok[0]['investors_passing']} investors into range."
                      if ok else "No price cut up to 30% reaches the guarantee. Widen the sector, ownership or financial evidence instead.")
    out = {"guarantee": guarantee, "investors_total": len(investors), "investors_passing": n, "status": status,
           "message": _message(n, guarantee, status),
           "investors_interested_in_sector": sum(listing["sector"] in i["sectors"] for i in investors),
           "exclusion_reasons": dict(reasons.most_common()), "what_if_price_cut": what_if, "suggestion": suggestion,
           "note": "Counts investors who pass hard filters. It does not predict that any of them will enquire or buy."}
    if top_k > 0 and passing:
        out["top_matches"] = M.rank_investors(listing, investors, scorer or M.RuleScorer(), top_k)["ranked"]
    return out
