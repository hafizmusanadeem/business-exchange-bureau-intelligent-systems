"""Module 5b: deterministic validation. Plain code recomputes every total; nothing here calls an LLM.
Flags are prompts for professional review, never accusations. Each flag cites the fact ids it rests on."""
from __future__ import annotations
from collections import defaultdict

SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}


def index(facts: list[dict]) -> dict:
    idx: dict = defaultdict(list)
    for f in facts: idx[(f["metric"], f["period"])].append(f)
    return idx


def best(idx, metric, period):
    c = idx.get((metric, period)); return max(c, key=lambda f: (f["confidence"], -f["page"])) if c else None


def derive_ebitda(idx, period) -> dict | None:
    g = lambda m: best(idx, m, period)
    if (e := g("ebitda")): return {"value": e["value"], "method": "reported", "approximate": False, "evidence": [e["id"]]}
    if (op := g("operating_profit")) and (d := g("depreciation")):
        return {"value": op["value"] + d["value"], "method": "operating_profit + depreciation", "approximate": False, "evidence": [op["id"], d["id"]]}
    gp = g("gross_profit"); rev, cos, ox = g("revenue"), g("cost_of_sales"), g("operating_expenses")
    base = gp["value"] if gp else (rev["value"] - cos["value"] if rev and cos else None)
    if base is not None and ox:
        ev = [x["id"] for x in (gp or rev, cos if not gp else None, ox) if x]
        return {"value": base - ox["value"], "method": "gross_profit - operating_expenses", "approximate": True, "evidence": ev,
                "note": "Assumes operating expenses exclude depreciation. Confirm with the seller."}
    if (te := g("total_expenses")) and rev:
        return {"value": rev["value"] - te["value"], "method": "revenue - total_expenses", "approximate": True, "evidence": [rev["id"], te["id"]],
                "note": "Total expenses may include depreciation, interest and tax, so this can understate EBITDA."}
    return None


def _flag(code, sev, msg, ev, **d): return {"code": code, "severity": sev, "message": msg, "evidence": ev, "details": d}


def validate(facts: list[dict], tol: float = 0.01) -> list[dict]:
    idx = index(facts); flags = []; periods = sorted({f["period"] for f in facts})
    g = lambda m, p: best(idx, m, p)
    fin = [p for p in periods if g("revenue", p)]
    if fin:
        want = [str(y) for y in range(int(fin[0]), int(fin[-1]) + 1)]
        if miss := [y for y in want if y not in fin]:
            flags.append(_flag("MISSING_PERIOD", "medium", f"No revenue found for {', '.join(miss)}. Request those statements.", [], missing=miss))
    for p in periods:
        rev, cos, gp = g("revenue", p), g("cost_of_sales", p), g("gross_profit", p)
        if rev and cos and gp and abs((rev["value"] - cos["value"]) - gp["value"]) > max(tol * rev["value"], 1):
            flags.append(_flag("GROSS_PROFIT_MISMATCH", "high", f"{p}: revenue minus cost of sales is {rev['value'] - cos['value']:,.0f} but gross profit is reported as {gp['value']:,.0f}.", [rev["id"], cos["id"], gp["id"]], period=p))
        ta, tl, te = g("total_assets", p), g("total_liabilities", p), g("total_equity", p)
        if ta and tl and te and abs(ta["value"] - tl["value"] - te["value"]) > max(tol * ta["value"], 1):
            flags.append(_flag("BALANCE_SHEET_MISMATCH", "high", f"{p}: assets {ta['value']:,.0f} differ from liabilities plus equity {tl['value'] + te['value']:,.0f}.", [ta["id"], tl["id"], te["id"]], period=p))
        rep, op, da = g("ebitda", p), g("operating_profit", p), g("depreciation", p)
        if rep and op and da and abs(rep["value"] - (op["value"] + da["value"])) > max(tol * abs(rep["value"]), 1):
            flags.append(_flag("EBITDA_MISMATCH", "medium", f"{p}: reported EBITDA {rep['value']:,.0f} differs from operating profit plus depreciation {op['value'] + da['value']:,.0f}.", [rep["id"], op["id"], da["id"]], period=p))
        e = derive_ebitda(idx, p)
        if e and rev and rev["value"] > 0:
            m = e["value"] / rev["value"]
            if e["value"] < 0: flags.append(_flag("NEGATIVE_EBITDA", "medium", f"{p}: EBITDA is negative ({e['value']:,.0f}).", e["evidence"], period=p))
            elif m > 0.6: flags.append(_flag("MARGIN_OUTLIER", "low", f"{p}: EBITDA margin of {m:.0%} is unusually high for an SME. Verify.", e["evidence"], period=p))
        bank = g("bank_deposits", p)
        if bank and rev and rev["value"] > 0:
            gap = (rev["value"] - bank["value"]) / rev["value"]
            if gap > 0.10:
                sev = "high" if gap > 0.25 else "medium"
                flags.append(_flag("REVENUE_BANK_GAP", sev, f"{p}: reported revenue {rev['value']:,.0f} but identifiable bank deposits are {bank['value']:,.0f} ({gap:.0%} lower). Cash sales, timing or other accounts may explain this. Needs professional review.", [rev["id"], bank["id"]], period=p, gap=round(gap, 3)))
            elif gap < -0.30:
                flags.append(_flag("DEPOSITS_EXCEED_REVENUE", "low", f"{p}: bank deposits exceed reported revenue by {-gap:.0%}. May include loans or transfers.", [rev["id"], bank["id"]], period=p))
    for a, b in zip(periods, periods[1:]):
        if int(b) - int(a) != 1: continue
        r0, r1, o0, o1 = g("revenue", a), g("revenue", b), g("operating_expenses", a), g("operating_expenses", b)
        if r0 and r1 and o0 and o1 and r0["value"] > 0 and o0["value"] > 0:
            rg, og = r1["value"] / r0["value"] - 1, o1["value"] / o0["value"] - 1
            if og - rg > 0.15 and og > 0.25:
                flags.append(_flag("EXPENSE_JUMP", "medium", f"{b}: operating expenses rose {og:.0%} while revenue rose {rg:.0%}. Ask for a breakdown.", [o0["id"], o1["id"], r0["id"], r1["id"]], period=b))
    for (m, p), fs in idx.items():  # conflicts between documents
        vals = [(f["value"], f) for f in fs]
        if len(vals) > 1 and max(v for v, _ in vals) - min(v for v, _ in vals) > tol * max(abs(v) for v, _ in vals) and len({f["file"] for _, f in vals}) >= 1 and len({v for v, _ in vals}) > 1:
            flags.append(_flag("CROSS_DOC_CONFLICT", "high", f"{m} for {p} appears with different values ({', '.join(f'{v:,.0f}' for v, _ in vals)}).", [f["id"] for _, f in vals], metric=m, period=p))
    if fin and not any(m == "bank_deposits" for m, _ in idx):
        flags.append(_flag("NO_BANK_EVIDENCE", "info", "No bank statement data supplied, so revenue is unverified by an independent source.", []))
    return sorted(flags, key=lambda f: SEV_ORDER[f["severity"]])


def quality_score(flags: list[dict]) -> int:
    return max(0, 100 - sum({"high": 25, "medium": 10, "low": 3, "info": 0}[f["severity"]] for f in flags))
