"""Offline evaluation on a SYNTHETIC ground truth. Run:  python -m app.bxb.eval_matching
The relevance labels come from a hidden utility function written for this demo (budget centrality, risk x margin,
location, noise). They are NOT BXB outcomes. The numbers show that the pipeline works and how to measure it;
they say nothing about real BXB performance. Replace labels with real offers and meetings when available."""
from __future__ import annotations
import json, random
import numpy as np
try:
    from app.bxb import matching as M, metrics as X
    from app.bxb.synthetic import generate
except ImportError:
    import matching as M, metrics as X
    from synthetic import generate


def latent_grade(l: dict, inv: dict, rng: random.Random) -> int:
    f = dict(zip(M.FEATURES, M.features(l, inv)))
    low, high = f["risk"] == 0, f["risk"] == 2
    u = (1.0 * (f["sector_rank"] == 2) + 0.5 * (f["sector_rank"] == 1) + 1.4 * f["budget_centrality"] + 0.8 * f["emirate_match"]
         + low * (6 * (f["margin"] - 0.2) + 1.0 * f["years"]) + high * 0.25 * (4 - f["multiple"]) + 0.4 * f["international"] * (f["margin"] > 0.2)
         + rng.gauss(0, 0.5))
    return 3 if u > 2.6 else 2 if u > 2.0 else 1 if u > 1.3 else 0


def build(seed: int = 7, n_listings: int = 700, min_cands: int = 6):
    d = generate(seed=seed); rng = random.Random(seed); invs = d["investors"]
    ls = [l for l in d["listings"] if l["ebitda"] > 0]; rng.shuffle(ls); out = []
    for l in ls[:n_listings * 2]:
        cands = [i for i in invs if not M.hard_filter(l, i)]
        if len(cands) >= min_cands:
            out.append((l, cands, [latent_grade(l, i, rng) for i in cands]))
        if len(out) == n_listings: break
    return out


def evaluate(seed: int = 7, k_boot: int = 1000) -> dict:
    data = build(seed); cut = int(len(data) * 0.7); train, test = data[:cut], data[cut:]   # split by LISTING
    Xtr = [M.features(l, i) for l, c, g in train for i in c]; ytr = [int(x >= 2) for l, c, g in train for x in g]
    learned = M.LearnedScorer.fit(Xtr, ytr, seed=0); rules = M.RuleScorer(); rng = random.Random(0)
    per = {"random": [], "rules": [], "learned": []}
    for l, c, g in test:
        if not any(x >= 2 for x in g): continue
        rs, ls_ = rules.score(l, c), learned.score(l, c)
        orders = {"random": rng.sample(range(len(c)), len(c)),
                  "rules": sorted(range(len(c)), key=lambda j: -rs[j]),
                  "learned": sorted(range(len(c)), key=lambda j: -ls_[j])}
        for n, o in orders.items():
            gr = [g[j] for j in o]
            per[n].append((X.precision_at_k(gr, 3), X.recall_at_k(gr, 10), X.ndcg_at_k(gr, 10)))
    mean = lambda n, m: float(np.mean([r[m] for r in per[n]]))
    res = {"note": "SYNTHETIC ground truth; not BXB performance", "train_listings": len(train), "test_listings_scored": len(per["rules"]),
           "avg_candidates_per_listing": round(float(np.mean([len(c) for _, c, _ in data])), 1),
           "metrics": {n: {"precision@3": round(mean(n, 0), 3), "recall@10": round(mean(n, 1), 3), "ndcg@10": round(mean(n, 2), 3)} for n in per}}
    a = np.array([r[2] for r in per["learned"]]) - np.array([r[2] for r in per["rules"]]); b = np.random.default_rng(0)
    boots = [a[b.integers(0, len(a), len(a))].mean() for _ in range(k_boot)]
    res["ndcg@10_learned_minus_rules"] = {"mean": round(float(a.mean()), 3), "ci95": [round(float(np.percentile(boots, 2.5)), 3), round(float(np.percentile(boots, 97.5)), 3)]}
    return res


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
