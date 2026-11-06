"""Unit tests for Module 2 – Investor Sentiment (no DB required)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.bxb import sentiment as S
from app.bxb.synthetic import generate


def ev(i, l, sec, d, q=True):
    return dict(
        investor_id=i, listing_id=l, sector=sec, qualified=q, occurred_on=d
    )


def test_views_never_count():
    e = [ev(1, 1, "A", date(2026, 4, 5), q=False)]
    assert S.sector_shares(e, *S.quarter_bounds("2026-Q2"))["n"] == 0


def test_unique_pairs_not_raw_events():
    e = [
        ev(1, 1, "A", date(2026, 4, 5)),
        ev(1, 1, "A", date(2026, 4, 9)),
        ev(2, 1, "A", date(2026, 5, 1)),
    ]
    r = S.sector_shares(e, *S.quarter_bounds("2026-Q2"))
    assert r["n"] == 2 and r["sectors"]["A"]["units"] == 2


def test_shares_sum_to_100():
    e = [ev(i, i, "AB"[i % 2], date(2026, 5, 1)) for i in range(40)]
    r = S.sector_shares(e, *S.quarter_bounds("2026-Q2"))
    assert abs(sum(v["share_pct"] for v in r["sectors"].values()) - 100) < 0.2


def test_quarter_bounds():
    assert S.quarter_bounds("2026-Q4") == (date(2026, 10, 1), date(2027, 1, 1))
    assert S.quarter_bounds("2026-Q1") == (date(2026, 1, 1), date(2026, 4, 1))


def test_wilson_and_ztest_sanity():
    lo, hi = S.wilson(50, 100)
    assert lo < 50 < hi
    assert S.two_prop_p(50, 100, 50, 100) > 0.99
    assert S.two_prop_p(10, 100, 40, 100) < 0.001


def test_small_noise_is_stable():
    e = (
        [ev(i, i, "A", date(2026, 1, 5)) for i in range(15)]
        + [ev(100 + i, i, "B", date(2026, 1, 5)) for i in range(15)]
        + [ev(i, i, "A", date(2026, 4, 5)) for i in range(16)]
        + [ev(100 + i, i, "B", date(2026, 4, 5)) for i in range(14)]
    )
    assert all(r["trend"] == "stable" for r in S.trend(e, "2026-Q1", "2026-Q2"))


def test_synthetic_healthcare_flagged_increasing():
    d = generate()
    inv = {i["id"]: i for i in d["investors"]}
    t = {r["sector"]: r for r in S.trend(d["events"], "2023-Q4", "2026-Q2")}
    assert t["Healthcare"]["trend"] == "increasing" and t["Healthcare"]["change_pts"] > 5
    f = S.facts(d["events"], inv, "2023-Q4", "2026-Q2")
    assert any(x["sector"] == "Healthcare" and "largest_growth_band" in x for x in f)


def test_segments_and_countries_nonempty():
    d = generate()
    inv = {i["id"]: i for i in d["investors"]}
    s, e = S.quarter_bounds("2026-Q2")
    assert S.country_mix(d["events"], inv, s, e) and S.segments(d["events"], inv, s, e)


def test_facts_have_no_duplicate_sectors():
    d = generate()
    inv = {i["id"]: i for i in d["investors"]}
    f = S.facts(d["events"], inv, "2023-Q4", "2026-Q2")
    assert len({x["sector"] for x in f}) == len(f) == 2
