"""Module 3b: forecasting with honest backtests. Pure Python so it runs anywhere.
Models: naive, seasonal naive (12), moving average (3), simple exp. smoothing, Holt-Winters (additive).
Selection: rolling-origin backtest (3-step-ahead). The chosen model must beat the best baseline
(naive / seasonal naive) by >= 5% MAE, otherwise the baseline is used and the output says so.
Prediction intervals come from the chosen model's backtest residuals (empirical 10th/90th percentile).
`forecast_with_statsforecast` is an optional adapter for Nixtla's statsforecast (same output shape); untested here."""
from __future__ import annotations
from itertools import product
from statistics import mean, median

SEASON = 12


def naive(y, h): return [y[-1]] * h
def seasonal_naive(y, h): return [y[len(y) - SEASON + (i % SEASON)] for i in range(h)] if len(y) >= SEASON else naive(y, h)
def moving_avg(y, h, k=3): return [mean(y[-k:])] * h


def ses(y, h):
    best = None
    for a in (0.1, 0.2, 0.3, 0.5, 0.7):
        lvl, sse = y[0], 0.0
        for v in y[1:]:
            sse += (v - lvl) ** 2; lvl = a * v + (1 - a) * lvl
        if best is None or sse < best[0]: best = (sse, lvl)
    return [best[1]] * h


def holt_winters(y, h):
    if len(y) < 2 * SEASON: return ses(y, h)
    best = None
    for a, b, g in product((0.2, 0.5, 0.8), (0.05, 0.2), (0.1, 0.3, 0.6)):
        lvl = mean(y[:SEASON]); tr = (mean(y[SEASON:2 * SEASON]) - mean(y[:SEASON])) / SEASON
        sea = [y[i] - lvl for i in range(SEASON)]; sse = 0.0
        for t in range(SEASON, len(y)):
            f = lvl + tr + sea[t % SEASON]; sse += (y[t] - f) ** 2
            nl = a * (y[t] - sea[t % SEASON]) + (1 - a) * (lvl + tr)
            tr = b * (nl - lvl) + (1 - b) * tr
            sea[t % SEASON] = g * (y[t] - nl) + (1 - g) * sea[t % SEASON]; lvl = nl
        if best is None or sse < best[0]: best = (sse, lvl, tr, list(sea), len(y))
    _, lvl, tr, sea, n = best
    return [lvl + (i + 1) * tr + sea[(n + i) % SEASON] for i in range(h)]


MODELS = {"naive": naive, "seasonal_naive": seasonal_naive, "moving_avg": moving_avg, "ses": ses, "holt_winters": holt_winters}


def backtest(y: list[float], horizon: int = 3, min_train: int = 24, models: dict | None = None) -> dict:
    models = models or MODELS
    res = {m: {"abs": [], "pct": [], "err": []} for m in models}
    for t in range(min_train, len(y) - horizon + 1):
        for m, f in models.items():
            fc = f(y[:t], horizon)
            for i in range(horizon):
                e = y[t + i] - fc[i]
                res[m]["abs"].append(abs(e)); res[m]["err"].append(e)
                if y[t + i] > 0: res[m]["pct"].append(abs(e) / y[t + i])
    return {m: {"mae": round(mean(r["abs"]), 3), "mape_pct": round(100 * mean(r["pct"]), 1) if r["pct"] else None,
                "n_forecasts": len(r["abs"]), "errors": r["err"]} for m, r in res.items() if r["abs"]}


def _q(sorted_vals, p): return sorted_vals[min(len(sorted_vals) - 1, max(0, int(p * (len(sorted_vals) - 1))))]


def forecast(y: list[float], horizon: int = 6, min_improvement: float = 0.05) -> dict:
    if len(y) < 12:
        return {"status": "insufficient_history", "n_points": len(y), "message": "Need at least 12 monthly points."}
    bt = backtest(y, horizon=min(3, horizon), min_train=min(24, max(12, len(y) - 6)))
    if not bt:
        return {"status": "insufficient_history", "n_points": len(y), "message": "Not enough history to backtest."}
    base = min((m for m in bt if m in ("naive", "seasonal_naive")), key=lambda m: bt[m]["mae"])
    cand = min(bt, key=lambda m: bt[m]["mae"])
    chosen, beats = base, False
    if cand != base and bt[cand]["mae"] <= bt[base]["mae"] * (1 - min_improvement):
        chosen, beats = cand, True
    pt = [max(0.0, v) for v in MODELS[chosen](y, horizon)]
    es = sorted(bt[chosen]["errors"]); lo, hi = _q(es, 0.1), _q(es, 0.9)
    return {"status": "ok", "model": chosen, "beats_baseline": beats, "baseline": base, "horizon": horizon,
            "forecast": [round(v, 1) for v in pt],
            "interval_80": [[round(max(0.0, v + lo), 1), round(v + hi, 1)] for v in pt],
            "backtest": {m: {k: v for k, v in r.items() if k != "errors"} for m, r in bt.items()},
            "note": "Intervals are empirical from backtest errors. If beats_baseline is false, a simple baseline is used on purpose."}


def forecast_with_statsforecast(y: list[float], horizon: int = 6) -> dict:  # optional, untested here
    import pandas as pd
    from statsforecast import StatsForecast
    from statsforecast.models import AutoETS, SeasonalNaive
    df = pd.DataFrame({"unique_id": "s", "ds": pd.date_range("2000-01-01", periods=len(y), freq="MS"), "y": y})
    out = StatsForecast(models=[AutoETS(season_length=12), SeasonalNaive(season_length=12)], freq="MS").forecast(df=df, h=horizon, level=[80])
    return {"status": "ok", "model": "AutoETS", "forecast": out["AutoETS"].round(1).tolist(),
            "interval_80": list(zip(out["AutoETS-lo-80"].round(1), out["AutoETS-hi-80"].round(1)))}
