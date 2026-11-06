"""Unit tests for Module 4 – Investor Matching (no DB required)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.bxb import eval_matching as E
from app.bxb import matching as M
from app.bxb import metrics as X
from app.bxb.synthetic import generate


def lst(**k):
    d = dict(
        id=1,
        sector="Healthcare",
        emirate="Dubai",
        asking_price=3_000_000,
        ebitda=400_000,
        annual_revenue=2_000_000,
        ownership_pct=100,
        years_operating=8,
    )
    return d | k


def inv(**k):
    d = dict(
        id=1,
        name="I1",
        country="UAE",
        budget_min=2_000_000,
        budget_max=5_000_000,
        sectors=["Healthcare"],
        emirates=["Dubai"],
        min_ebitda=250_000,
        risk_appetite="low",
    )
    return d | k


def test_hard_filters():
    assert M.hard_filter(lst(), inv()) == []
    assert "sector outside stated preferences" in M.hard_filter(lst(sector="Retail"), inv())
    assert "asking price above budget" in M.hard_filter(lst(asking_price=9_000_000), inv())
    assert "EBITDA below investor minimum" in M.hard_filter(lst(ebitda=100_000), inv())
    assert M.hard_filter(lst(asking_price=5_400_000), inv()) == []  # inside 10% tolerance


def test_metrics_hand_checked():
    g = [3, 0, 2, 0]
    assert abs(X.precision_at_k(g, 3) - 2 / 3) < 1e-9
    assert X.recall_at_k(g, 2) == 0.5
    assert abs(X.ndcg_at_k(g, 4) - 8.5 / (7 + 3 / 1.5849625007)) < 1e-4
    assert X.ndcg_at_k([3, 2, 0, 0], 4) == 1.0
    assert X.ndcg_at_k([0, 0], 2) == 0.0


def test_rank_never_returns_excluded_and_is_sorted():
    investors = [
        inv(id=1),
        inv(id=2, sectors=["Retail"]),
        inv(id=3, budget_min=100_000, budget_max=500_000),
        inv(id=4, emirates=["Sharjah"]),
    ]
    r = M.rank_investors(lst(), investors, M.RuleScorer())
    ids = [x["investor_id"] for x in r["ranked"]]
    assert set(ids) == {1, 4} and ids[0] == 1 and r["excluded"] == 2
    assert r["ranked"][0]["score"] >= r["ranked"][1]["score"]
    assert r["ranked"][0]["reasons"]


def test_rule_score_bounds():
    s, comp = M.rule_score(lst(), inv())
    assert 0 < s <= 100
    assert set(comp) == {"sector", "budget", "location", "risk_fit"}


def test_features_length_and_edge_cases():
    assert len(M.features(lst(ebitda=0), inv(min_ebitda=0, budget_min=2e6, budget_max=2e6))) == len(M.FEATURES)


def test_pipeline_beats_random_on_synthetic_ground_truth():
    r = E.evaluate(seed=3, k_boot=50)["metrics"]
    assert r["rules"]["ndcg@10"] > r["random"]["ndcg@10"] + 0.1
    assert r["learned"]["ndcg@10"] > r["random"]["ndcg@10"] + 0.1


def test_save_load_roundtrip():
    d = generate(n_investors=60)
    invs = d["investors"]
    ls = d["listings"][:3]
    X_, y = M.pairs_from_events(d["listings"], invs, d["events"])
    s = M.LearnedScorer.fit(X_, y)
    p = os.path.join(tempfile.mkdtemp(), "m.joblib")
    s.save(p)
    s2 = M.LearnedScorer.load(p)
    assert s.score(ls[0], invs[:5]) == s2.score(ls[0], invs[:5])


def test_pairs_from_events_has_both_classes():
    d = generate(n_investors=100)
    X_, y = M.pairs_from_events(d["listings"], d["investors"], d["events"])
    assert len(X_) == len(y) and 0 < sum(y) < len(y)
