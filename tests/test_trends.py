"""Unit tests for Module 3 – Sale Trends, Demand vs Supply, Forecasting (no DB required)."""
from __future__ import annotations

import math
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.bxb import forecast as F, trends as T
from app.bxb.synthetic import generate


def L(i, sec, ask, listed, closed=None, status="active", ebitda=100, rev=400, em="Dubai"):
    return dict(
        id=i,
        sector=sec,
        emirate=em,
        asking_price=ask,
        listed_on=listed,
        closed_on=closed,
        status=status,
        ebitda=ebitda,
        annual_revenue=rev,
    )


def test_median_resists_outlier():
    ls = [
        L(i, "X", p, date(2026, 5, 1))
        for i, p in enumerate([500_000, 700_000, 800_000, 1_000_000, 20_000_000])
    ]
    s = T.market_stats(ls, [], date(2026, 6, 30), "X")["asking_price_aed"]
    assert s["median"] == 800_000 and s["mean"] == 4_600_000 and s["max"] == 20_000_000


def test_active_excludes_closed():
    ls = [
        L(1, "X", 1, date(2026, 1, 1)),
        L(2, "X", 1, date(2026, 1, 1), closed=date(2026, 3, 1), status="sold"),
    ]
    assert T.market_stats(ls, [], date(2026, 6, 30))["active_listings"] == 1


def test_days_to_close_and_multiples():
    ls = [
        L(1, "X", 400, date(2026, 1, 1), closed=date(2026, 3, 2), status="sold"),
        L(2, "X", 400, date(2026, 5, 1), ebitda=100, rev=400),
    ]
    m = T.market_stats(ls, [], date(2026, 6, 30))
    assert m["median_days_to_close"] == 60 and m["asking_to_ebitda_x"]["median"] == 4.0


def test_conversion_counts_only_qualified():
    ls = [L(1, "X", 1, date(2026, 6, 1)), L(2, "X", 1, date(2026, 6, 2))]
    ev = [
        dict(listing_id=1, qualified=True, occurred_on=date(2026, 6, 10)),
        dict(listing_id=2, qualified=False, occurred_on=date(2026, 6, 10)),
    ]
    assert T.market_stats(ls, ev, date(2026, 6, 30))["conversion_rate_pct"] == 50.0


def test_zero_division_safe():
    m = T.market_stats([], [], date(2026, 6, 30))
    assert m["active_listings"] == 0
    assert m["conversion_rate_pct"] is None
    assert m["new_listings_change_pct"] is None


def test_demand_vs_supply_on_synthetic():
    d = generate()
    r = {x["sector"]: x for x in T.demand_vs_supply(d["listings"], d["events"], "2026-Q2")}
    assert abs(sum(x["demand_share_pct"] for x in r.values()) - 100) < 0.6
    assert r["Healthcare"]["label"] == "under-supplied"
    assert r["Information Technology"]["label"] == "over-supplied"


def test_monthly_series_fills_gaps():
    ls = [L(1, "X", 1, date(2026, 1, 5)), L(2, "X", 1, date(2026, 4, 5))]
    s = T.monthly_series(ls, "X")
    assert [v for _, v in s] == [1, 0, 0, 1]


def test_forecast_constant_series_is_exact():
    r = F.forecast([10.0] * 36, 6)
    assert r["status"] == "ok" and all(abs(v - 10) < 1e-6 for v in r["forecast"])


def test_forecast_learns_seasonality_and_never_negative():
    y = [50 + 20 * math.sin(2 * math.pi * i / 12) + i * 0.3 for i in range(48)]
    r = F.forecast(y, 6)
    assert r["model"] in ("seasonal_naive", "holt_winters")
    assert r["backtest"][r["model"]]["mae"] < r["backtest"]["naive"]["mae"]
    assert all(v >= 0 for v in r["forecast"])
    assert all(lo <= p <= hi for p, (lo, hi) in zip(r["forecast"], r["interval_80"]))


def test_forecast_refuses_short_history():
    assert F.forecast([1.0] * 8)["status"] == "insufficient_history"


def test_forecast_on_synthetic_runs_and_reports_baseline():
    d = generate()
    ser = [v for _, v in T.monthly_series(d["listings"], None)]
    r = F.forecast(ser, 6)
    assert r["status"] == "ok" and len(r["forecast"]) == 6 and "naive" in r["backtest"]
