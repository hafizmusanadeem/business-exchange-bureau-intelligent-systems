"""Module 5c: preliminary valuation scenarios. NOT a professional valuation (BXB offers expert-reviewed ones).
ASSUMPTIONS ARE PLACEHOLDERS: multiples and discount rates below are illustrative defaults for a demo and must be
replaced with BXB comparable-transaction evidence. Real evidence and assumptions are kept visibly separate."""
from __future__ import annotations

PLACEHOLDER_MULTIPLES = {"Food & Beverage": (2.5, 3.5, 4.5), "Healthcare": (4.0, 5.5, 7.0), "Information Technology": (3.0, 4.5, 6.0),
                         "Beauty": (2.0, 3.0, 4.0), "Retail": (1.8, 2.8, 3.8), "Logistics": (3.0, 4.0, 5.0), "Commercial Services": (2.5, 3.5, 4.5)}
DEFAULT_MULTIPLES = (2.5, 3.5, 4.5)
SCENARIOS = {"conservative": dict(r=0.20, tg=0.02, conv=0.50, g_cap=0.03), "base": dict(r=0.16, tg=0.025, conv=0.60, g_cap=0.10),
             "optimistic": dict(r=0.13, tg=0.03, conv=0.70, g_cap=0.15)}


def cagr(first: float, last: float, years: int) -> float | None:
    return (last / first) ** (1 / years) - 1 if years > 0 and first > 0 and last > 0 else None


def dcf(ebitda: float, g0: float, r: float, tg: float, conv: float, years: int = 5) -> float:
    """EV = sum FCF_t / (1+r)^t + TV / (1+r)^n, FCF = EBITDA * cash conversion, growth fading linearly g0 -> tg."""
    if r <= tg: raise ValueError("discount rate must exceed terminal growth")
    e, pv = ebitda, 0.0
    for t in range(1, years + 1):
        g = g0 + (tg - g0) * (t - 1) / max(years - 1, 1); e *= 1 + g; pv += e * conv / (1 + r) ** t
    return pv + (e * conv * (1 + tg) / (r - tg)) / (1 + r) ** years


def valuate(ebitda: float | None, sector: str, history: dict | None = None, asking: float | None = None, net_debt: float | None = None,
            quality: int = 100, flags: list[dict] | None = None, approximate_ebitda: bool = False) -> dict:
    if ebitda is None or ebitda <= 0:
        return {"status": "not_meaningful", "message": "EBITDA is missing or not positive, so an EBITDA-based valuation is not meaningful. Use revenue or asset approaches with a professional."}
    lo, mid, hi = PLACEHOLDER_MULTIPLES.get(sector, DEFAULT_MULTIPLES); h = history or {}
    ys = sorted(h); gh = cagr(h[ys[0]], h[ys[-1]], int(ys[-1]) - int(ys[0])) if len(ys) >= 2 else None
    out = {"status": "ok", "ebitda": round(ebitda), "ebitda_approximate": approximate_ebitda, "sector": sector, "historical_ebitda_cagr": round(gh, 4) if gh is not None else None,
           "multiples": {"conservative": lo, "base": mid, "optimistic": hi}, "multiples_are_placeholders": True, "scenarios": {}}
    for name, mult in zip(SCENARIOS, (lo, mid, hi)):
        p = SCENARIOS[name]; g0 = max(-0.05, min(p["g_cap"], gh if gh is not None else 0.03))
        ev_m = ebitda * mult; ev_d = dcf(ebitda, g0, p["r"], p["tg"], p["conv"]); ev = (ev_m + ev_d) / 2
        eq = ev - net_debt if net_debt is not None else None
        out["scenarios"][name] = {"ev_multiple": round(ev_m), "ev_dcf": round(ev_d), "enterprise_value": round(ev), "equity_value": round(eq) if eq is not None else None,
                                  "assumptions": {"multiple": mult, "discount_rate": p["r"], "terminal_growth": p["tg"], "cash_conversion": p["conv"], "start_growth": round(g0, 4)}}
    evs = [s["enterprise_value"] for s in out["scenarios"].values()]
    out["range_ev"] = [min(evs), max(evs)]; out["method_note"] = "Enterprise value = average of EBITDA-multiple and DCF values in each scenario."
    out["sensitivity_ev_multiple"] = [{"ebitda_change_pct": d, **{f"{m}x": round(ebitda * (1 + d / 100) * m) for m in (lo, mid, hi)}} for d in (-10, 0, 10)]
    out["sensitivity_dcf_base"] = [{"discount_rate": r, **{f"growth_{g}": round(dcf(ebitda, g, r, 0.025, 0.6)) for g in (0.0, 0.05, 0.10)}} for r in (0.13, 0.16, 0.20)]
    high = [f for f in (flags or []) if f["severity"] == "high"]
    out["confidence"] = "low" if high or quality < 60 or approximate_ebitda and quality < 80 else "medium" if quality < 90 or approximate_ebitda else "preliminary"
    out["data_quality_score"] = quality
    out["warnings"] = ([f"{len(high)} high-severity data flag(s): resolve before relying on this valuation."] if high else []) + (["EBITDA was derived approximately."] if approximate_ebitda else []) + ["Multiples and rates are placeholders, not transaction evidence."]
    if asking:
        b = out["scenarios"]["base"]["enterprise_value"]
        out["asking_vs_range"] = {"asking": asking, "position": "below range" if asking < out["range_ev"][0] else "above range" if asking > out["range_ev"][1] else "within range", "asking_to_base_pct": round(100 * asking / b)}
    return out
