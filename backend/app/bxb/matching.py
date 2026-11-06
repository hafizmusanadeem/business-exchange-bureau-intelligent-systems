"""Module 4: investor-business matching. Two stages, because this is a ranking problem, not just similarity:
  1) HARD FILTERS (explainable, never overridden by a model): sector in the investor's preferences,
     asking price within budget (15% lower / 10% upper tolerance), EBITDA >= investor minimum.
  2) RANKING of the survivors by a scorer: transparent rule score (baseline) or a learned gradient-boosted model.
Explanations always come from stated, checkable facts about the pair, not from the model internals."""
from __future__ import annotations
import numpy as np

FEATURES = ["sector_rank", "budget_pos", "budget_centrality", "over_budget", "under_budget", "emirate_match", "ebitda_ratio",
            "margin", "multiple", "risk", "ownership", "years", "international", "log_ask"]
RISK = {"low": 0, "medium": 1, "high": 2}


def hard_filter(l: dict, inv: dict) -> list[str]:
    """Returns the reasons an investor is excluded (empty list = passes)."""
    why = []
    if l["sector"] not in inv["sectors"]: why.append("sector outside stated preferences")
    if l["asking_price"] > inv["budget_max"] * 1.10: why.append("asking price above budget")
    if l["asking_price"] < inv["budget_min"] * 0.85: why.append("asking price well below budget range")
    if l["ebitda"] < inv["min_ebitda"]: why.append("EBITDA below investor minimum")
    return why


def features(l: dict, inv: dict) -> list[float]:
    lo, hi, ask = inv["budget_min"], inv["budget_max"], l["asking_price"]
    pos = (ask - lo) / (hi - lo) if hi > lo else 0.5
    sr = 2 if inv["sectors"][:1] == [l["sector"]] else 1 if l["sector"] in inv["sectors"] else 0
    ebitda, rev = l["ebitda"], max(l["annual_revenue"], 1)
    return [sr, pos, 1 - min(1.0, abs(pos - 0.5) * 2), max(0.0, ask / hi - 1) if hi else 0.0, max(0.0, 1 - ask / lo) if lo else 0.0,
            float(l["emirate"] in inv["emirates"]), min(5.0, ebitda / inv["min_ebitda"]) if inv["min_ebitda"] else 5.0,
            ebitda / rev, min(20.0, ask / ebitda) if ebitda > 0 else 20.0, RISK[inv["risk_appetite"]], l["ownership_pct"] / 100,
            min(l["years_operating"], 30) / 30, float(inv["country"] != "UAE"), float(np.log10(max(ask, 1)))]


def rule_score(l: dict, inv: dict) -> tuple[float, dict]:
    f = dict(zip(FEATURES, features(l, inv)))
    comp = {"sector": 40 if f["sector_rank"] == 2 else 25 if f["sector_rank"] == 1 else 0,
            "budget": 30 if inv["budget_min"] <= l["asking_price"] <= inv["budget_max"] else 14 if (f["over_budget"] or f["under_budget"]) and not (f["over_budget"] > .1) else 0,
            "location": 15 if f["emirate_match"] else 0,
            "risk_fit": (15 if inv["risk_appetite"] == "high" else 12 if inv["risk_appetite"] == "medium" else 9) if l["ebitda"] >= inv["min_ebitda"] else 0}
    return float(sum(comp.values())), comp


def explain(l: dict, inv: dict) -> list[str]:
    out = []
    if inv["sectors"][:1] == [l["sector"]]: out.append(f"{l['sector']} is a primary sector for this investor")
    elif l["sector"] in inv["sectors"]: out.append(f"{l['sector']} is a secondary sector for this investor")
    if inv["budget_min"] <= l["asking_price"] <= inv["budget_max"]:
        out.append(f"asking price AED {l['asking_price']:,} sits inside the AED {inv['budget_min']:,} to {inv['budget_max']:,} budget")
    else: out.append("asking price is slightly outside the stated budget")
    if l["emirate"] in inv["emirates"]: out.append(f"investor prefers {l['emirate']}")
    out.append(f"EBITDA AED {l['ebitda']:,} meets the AED {inv['min_ebitda']:,} minimum")
    return out


class RuleScorer:
    name = "rules"
    def score(self, l, invs): return [rule_score(l, i)[0] for i in invs]


class LearnedScorer:
    """Gradient-boosted classifier on pair features. Swap-in alternative: LightGBM LGBMRanker on the same FEATURES."""
    name = "learned"
    def __init__(self, model=None): self.model = model
    def score(self, l, invs):
        X = np.array([features(l, i) for i in invs])
        return self.model.predict_proba(X)[:, 1].tolist()
    @classmethod
    def fit(cls, X, y, seed: int = 0):
        from sklearn.ensemble import HistGradientBoostingClassifier
        m = HistGradientBoostingClassifier(max_iter=150, learning_rate=0.08, max_depth=4, random_state=seed)
        m.fit(np.asarray(X), np.asarray(y)); return cls(m)
    def save(self, path): import joblib; joblib.dump(self.model, path)
    @classmethod
    def load(cls, path): import joblib; return cls(joblib.load(path))


def rank_investors(l: dict, investors: list[dict], scorer, k: int = 10) -> dict:
    ok, excluded = [], []
    for inv in investors:
        why = hard_filter(l, inv)
        (excluded if why else ok).append((inv, why))
    scores = scorer.score(l, [i for i, _ in ok]) if ok else []
    ranked = sorted(zip(ok, scores), key=lambda t: -t[1])[:k]
    return {"listing_id": l["id"], "scorer": scorer.name, "candidates": len(ok), "excluded": len(excluded),
            "ranked": [{"rank": r + 1, "investor_id": inv["id"], "name": inv["name"], "country": inv["country"], "score": round(float(s), 4),
                        "reasons": explain(l, inv)} for r, ((inv, _), s) in enumerate(ranked)]}


def pairs_from_events(listings: list[dict], investors: list[dict], events: list[dict], neg_per_pos: int = 3, seed: int = 0):
    """PRODUCTION training set from real behaviour. Positive = qualified event (grade by kind).
    Negatives = hard-filter-passing pairs with no event. Caveat: absence of an event is not proof of disinterest
    (positive-unlabeled), so treat the learned score as a ranking signal, not a probability."""
    import random
    rng = random.Random(seed); L = {l["id"]: l for l in listings}; I = {i["id"]: i for i in investors}
    pos = {}
    for e in events:
        if e["qualified"] and e["listing_id"] in L and e["investor_id"] in I and not hard_filter(L[e["listing_id"]], I[e["investor_id"]]):
            pos[(e["investor_id"], e["listing_id"])] = 1  # same population as the negatives: ranking happens after filtering
    X, y = [], []
    for (i, l) in pos:
        X.append(features(L[l], I[i])); y.append(1)
    keys = list(pos); lids = list(L)
    for _ in range(len(keys) * neg_per_pos):
        i = rng.choice(keys)[0]; l = rng.choice(lids)
        if (i, l) not in pos and not hard_filter(L[l], I[i]):
            X.append(features(L[l], I[i])); y.append(0)
    return X, y
