import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "backend/app/bxb"))
from synthetic import generate
from collections import Counter

def share(events, quarter_months):
    q = [e for e in events if e["qualified"] and e["occurred_on"].strftime("%Y-%m") in quarter_months]
    c = Counter(e["sector"] for e in q); t = sum(c.values()) or 1
    return {s: c[s] / t for s in c}

def test_deterministic():
    a, b = generate(seed=1, n_investors=50), generate(seed=1, n_investors=50)
    assert a["listings"] == b["listings"] and a["events"] == b["events"]

def test_sizes_and_integrity():
    d = generate(n_investors=200)
    ids = {l["id"] for l in d["listings"]}
    assert len(d["listings"]) > 1000 and len(d["events"]) > 1000
    assert all(e["listing_id"] in ids for e in d["events"])
    assert all(l["ebitda"] < l["annual_revenue"] for l in d["listings"])
    assert all((l["closed_on"] is None) == (l["status"] == "active") for l in d["listings"])

def test_planted_trends_are_detectable():
    d = generate(n_investors=500)
    first = [f"2023-{m:02d}" for m in (10, 11, 12)]; last = [f"2026-{m:02d}" for m in (4, 5, 6)]
    a, b = share(d["events"], first), share(d["events"], last)
    assert b.get("Healthcare", 0) > a.get("Healthcare", 0)
    assert b.get("Retail", 0) < a.get("Retail", 0)
