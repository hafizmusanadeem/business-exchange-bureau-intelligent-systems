"""Builds synthetic financial-statement PDFs in several layouts (known ground truth) and scores the extractor.
Run:  python -m app.bxb.finance_synth      ALL DOCUMENTS ARE SYNTHETIC."""
from __future__ import annotations
import json, random, tempfile, os
try:
    from app.bxb import finance_extract as FE, finance_validate as FV
except ImportError:
    import finance_extract as FE, finance_validate as FV
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INCOME = ["revenue", "cost_of_sales", "gross_profit", "operating_expenses", "depreciation", "operating_profit", "net_profit"]
BALANCE = ["total_assets", "total_liabilities", "total_equity"]
NAMES = {"A": dict(revenue="Revenue", cost_of_sales="Cost of sales", gross_profit="Gross profit", operating_expenses="Operating expenses", depreciation="Depreciation",
                   operating_profit="Operating profit", net_profit="Net profit", total_assets="Total assets", total_liabilities="Total liabilities", total_equity="Total equity"),
         "B": dict(revenue="Turnover", cost_of_sales="Direct costs", gross_profit="Gross profit", operating_expenses="Administrative expenses", depreciation="Depreciation and amortisation",
                   operating_profit="Profit from operations", net_profit="Profit for the year", total_assets="Total assets", total_liabilities="Total liabilities", total_equity="Total shareholders' equity"),
         "C": dict(revenue="Net sales", cost_of_sales="Cost of goods sold", gross_profit="Gross margin", operating_expenses="General and administrative expenses", depreciation="Depreciation",
                   operating_profit="Operating income", net_profit="Net income", total_assets="Total assets", total_liabilities="Total liabilities", total_equity="Total equity")}


def make_truth(rng: random.Random, years=(2023, 2024, 2025)) -> dict:
    t, rev = {}, rng.uniform(1.5e6, 6e6); c0, o0, d0 = rng.uniform(0.35, 0.5), rng.uniform(0.2, 0.3), rng.uniform(0.01, 0.03)  # company-level cost structure
    for y in years:
        rev *= rng.uniform(1.05, 1.25); cos = rev * c0 * rng.uniform(0.97, 1.03); opx = rev * o0 * rng.uniform(0.95, 1.05); dep = rev * d0 * rng.uniform(0.95, 1.05)
        gp = rev - cos; op = gp - opx - dep; ta = rev * rng.uniform(0.8, 1.4); tl = ta * rng.uniform(0.3, 0.6)
        t[str(y)] = {k: round(v) for k, v in dict(revenue=rev, cost_of_sales=cos, gross_profit=gp, operating_expenses=opx, depreciation=dep, operating_profit=op,
                                                  net_profit=op * 0.9, total_assets=ta, total_liabilities=tl, total_equity=ta - tl).items()}
        t[str(y)]["bank_deposits"] = round(rev * rng.uniform(0.95, 1.05))
    return t


def _fmt(v, layout, metric):
    x = v / 1000 if layout == "B" else v; s = f"{x:,.0f}"
    if layout == "B" and metric in FE.COST_METRICS: return f"({s})"
    if layout == "C": return f"AED {s}"
    return s


def build_pdf(path: str, truth: dict, layout: str = "A", bank: bool = False, grid: bool = True) -> None:
    ys = sorted(truth) if layout != "C" else sorted(truth, reverse=True); st = getSampleStyleSheet()
    hdr = (["Item"] + ys) if layout != "C" else (["Item", "Notes"] + [f"FY{y}" for y in ys])
    def tbl(keys):
        rows = [hdr]
        for i, k in enumerate(keys):
            r = [NAMES[layout][k]] + ([str(i + 2)] if layout == "C" else []) + [_fmt(truth[y][k], layout, k) for y in ys]; rows.append(r)
        t = Table(rows); t.setStyle(TableStyle(([("GRID", (0, 0), (-1, -1), 0.5, colors.black)] if grid else [("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black)]) + [("FONTSIZE", (0, 0), (-1, -1), 9)])); return t
    title = {"A": "Income Statement (AED)", "B": "Income Statement - AED '000", "C": "Statement of Comprehensive Income"}[layout]
    doc = [Paragraph(title, st["Title"]), tbl(INCOME)]
    if layout == "C": doc += [PageBreak(), Paragraph("Statement of Financial Position", st["Title"]), tbl(BALANCE)]
    else: doc += [Spacer(1, 20), Paragraph("Balance Sheet", st["Heading2"]), tbl(BALANCE)]
    if bank:
        rows = [["Item"] + sorted(truth)] + [["Total credits"] + [f"{truth[y]['bank_deposits']:,.0f}" for y in sorted(truth)]]
        t = Table(rows); t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
        doc += [PageBreak(), Paragraph("Bank statement summary (AED)", st["Title"]), t]
    SimpleDocTemplate(path, pagesize=A4).build(doc)


def score(truth: dict, facts: list[dict], tol: float = 0.005, unit: float = 1.0, skip: tuple = ()) -> tuple[int, int]:
    got = {(f["metric"], f["period"]): f["value"] for f in facts}; ok = tot = 0
    for y, row in truth.items():
        for m, v in row.items():
            if m in skip: continue
            tot += 1; g = got.get((m, y)); ok += g is not None and abs(g - v) <= max(tol * abs(v), unit / 2)  # statements printed in thousands are rounded to the unit
    return ok, tot


def evaluate(n_per_layout: int = 10, seed: int = 1) -> dict:
    rng = random.Random(seed); d = tempfile.mkdtemp(); res = {}
    for layout in "ABC":
        ok = tot = 0
        for i in range(n_per_layout):
            t = make_truth(rng); p = os.path.join(d, f"{layout}{i}.pdf"); build_pdf(p, t, layout, bank=True)
            o, n = score(t, FE.extract_pdf(p)["facts"], unit=1000.0 if layout == "B" else 1.0); ok += o; tot += n
        res[layout] = {"field_accuracy": round(ok / tot, 4), "fields": tot}
    res["overall_field_accuracy"] = round(sum(r["field_accuracy"] * r["fields"] for r in res.values()) / sum(r["fields"] for r in res.values()), 4)
    ok = tot = 0   # same statements, but WITHOUT ruled table lines (text-alignment fallback)
    for layout in "ABC":
        for i in range(n_per_layout):
            t = make_truth(rng); p = os.path.join(d, f"ng{layout}{i}.pdf"); build_pdf(p, t, layout, bank=False, grid=False)
            o, n = score(t, FE.extract_pdf(p)["facts"], unit=1000.0 if layout == "B" else 1.0, skip=("bank_deposits",)); ok += o; tot += n
    res["no_ruled_lines_field_accuracy"] = {"field_accuracy": round(ok / tot, 4), "fields": tot}
    # validator detection on planted errors (end to end through PDFs)
    cases = {"GROSS_PROFIT_MISMATCH": lambda t: t["2025"].update(gross_profit=round(t["2025"]["gross_profit"] * 1.12)),
             "REVENUE_BANK_GAP": lambda t: [t[y].update(bank_deposits=round(t[y]["revenue"] * 0.7)) for y in t],
             "BALANCE_SHEET_MISMATCH": lambda t: t["2024"].update(total_equity=round(t["2024"]["total_equity"] * 0.8)),
             "EXPENSE_JUMP": lambda t: t["2025"].update(operating_expenses=round(t["2024"]["operating_expenses"] * 1.8))}
    det = {k: 0 for k in cases}; fp = 0; n = 12
    for i in range(n):
        t = make_truth(rng); p = os.path.join(d, f"clean{i}.pdf"); build_pdf(p, t, "A", bank=True)
        fp += any(f["severity"] in ("high", "medium") for f in FV.validate(FE.extract_pdf(p)["facts"]))
        for code, mut in cases.items():
            tt = json.loads(json.dumps(t)); mut(tt); p2 = os.path.join(d, f"{code}{i}.pdf"); build_pdf(p2, tt, "A", bank=True)
            det[code] += any(f["code"] == code for f in FV.validate(FE.extract_pdf(p2)["facts"]))
    res["validator"] = {"cases_per_error": n, "detection_rate": {k: round(v / n, 2) for k, v in det.items()}, "clean_docs_with_false_alarm": f"{fp}/{n}"}
    res["note"] = "Synthetic, cleanly ruled tables. Real scanned or irregular statements will score lower; measure on real documents."
    return res


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
