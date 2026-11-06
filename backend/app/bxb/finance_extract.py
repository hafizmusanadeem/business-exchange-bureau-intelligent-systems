"""Module 5a: financial table extraction with provenance.
Pipeline: PDF -> tables (pdfplumber; Docling is the intended heavier alternative via the same Fact format)
-> year columns -> deterministic label mapping -> numbers (units, brackets, currency) -> Facts.
Every Fact keeps file, page, table, row, column, bbox and the raw cell text, so each figure is traceable.
An optional `label_mapper` (e.g. an LLM call) may classify labels the rules could not map; those facts carry
mapped_by="llm" and lower confidence. LLMs never do arithmetic here: see finance_validate.py."""
from __future__ import annotations
import re
from dataclasses import asdict, dataclass, field

COST_METRICS = {"cost_of_sales", "operating_expenses", "depreciation", "interest_expense", "tax", "total_expenses"}
LABELS = [  # ordered: first match wins
    ("gross_profit", r"gross (profit|margin)"), ("cost_of_sales", r"(cost of (sales|revenue|goods sold|services)|direct costs?|cogs)"),
    ("ebitda", r"ebitda|earnings before interest, tax"), ("operating_profit", r"(operating (profit|income)|profit from operations|\bebit\b)"),
    ("depreciation", r"(depreciation|amorti[sz]ation)"), ("total_expenses", r"total expenses"),
    ("operating_expenses", r"((operating|administrative|admin|general( and| &) administrative|selling).*(expenses|costs)|opex)"),
    ("interest_expense", r"((finance|interest) (costs?|expenses?)|interest paid)"), ("tax", r"(income tax|corporate tax|tax expense|taxation)"),
    ("net_profit", r"(net (profit|income|earnings)|profit for the (year|period)|profit after tax)"),
    ("total_assets", r"total assets"), ("total_liabilities", r"total liabilities"), ("total_equity", r"total (shareholders'? )?equity"),
    ("bank_deposits", r"^(total )?(credits|deposits)( received)?"), ("debt", r"^(bank (loans?|borrowings)|borrowings|total debt)"),
    ("cash", r"^cash( and (cash )?equivalents| at bank)?"),
]
REVENUE_RE = re.compile(r"(total |net )?(revenues?|sales|turnover)( \(net\))?")
YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


@dataclass
class Fact:
    id: int; metric: str; period: str; value: float; raw: str; label: str
    file: str; page: int; table: int; row: int; col: int; bbox: list | None
    scale: float = 1.0; confidence: float = 1.0; mapped_by: str = "rules"


def clean_label(s: str) -> str:
    s = re.sub(r"\(.*?\)", " ", (s or "").lower()); s = re.sub(r"[:\u2013\u2014]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def map_label(label: str) -> str | None:
    c = clean_label(label)
    if not c: return None
    for metric, rx in LABELS:
        if (re.fullmatch(rx[1:], c) if rx.startswith("^") else re.fullmatch(rf".*{rx}.*", c)): return metric
    return "revenue" if REVENUE_RE.fullmatch(c) else None


def parse_number(s: str | None) -> float | None:
    if s is None: return None
    t = str(s).strip()
    if not t or "%" in t or t in {"-", "\u2013", "\u2014", "n/a", "N/A"}: return None
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-") or t.startswith("\u2212") or t.endswith("-")
    t = re.sub(r"(?i)\b(aed|usd|dhs?|dirhams?)\b|[$\u20ac\u00a3(),\s\-\u2212\u2013]", "", t)
    mult = 1.0
    if t[-1:].lower() in "mk" and len(t) > 1: mult = 1e6 if t[-1].lower() == "m" else 1e3; t = t[:-1]
    try: v = float(t) * mult
    except ValueError: return None
    return -v if neg else v


def detect_scale(text: str) -> float:
    t = text.lower()
    if re.search(r"(in|aed|usd)\s*(millions|m\b)|\bmillions\b|'000,000", t): return 1e6
    if re.search(r"thousands|'000|\u2019000|\b000s\b|aed\s*k\b", t): return 1e3
    return 1.0


def _years(row: list) -> dict[int, str]:
    out = {}
    for j, c in enumerate(row):
        if j == 0 or not c: continue
        m = YEAR_RE.findall(str(c))
        if m and len(str(c).strip()) <= 22: out[j] = m[-1]
    return out


def extract_pdf(path: str, label_mapper=None, max_pages: int = 60, file_name: str | None = None) -> dict:
    import pdfplumber
    facts: list[Fact] = []; unmapped: list[dict] = []; warnings: list[str] = []; fid = 0; name = file_name or path.rsplit("/", 1)[-1]
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) > max_pages: raise ValueError(f"PDF has more than {max_pages} pages")
        for pno, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            def process(tables) -> int:
                nonlocal fid
                n0 = len(facts)
                for ti, tbl in enumerate(tables):
                    rows = tbl.extract(); trows = getattr(tbl, "rows", [])
                    hdr = next((i for i, r in enumerate(rows) if len(_years(r)) >= 1), None)
                    if hdr is None: continue
                    years = _years(rows[hdr]); scale = detect_scale(text[:700] + " " + " ".join(str(c) for c in rows[0] if c))
                    for ri in range(hdr + 1, len(rows)):
                        label = rows[ri][0] or ""; metric = map_label(label)
                        if metric is None and clean_label(label):
                            unmapped.append({"label": label, "page": pno, "table": ti, "row": ri}); continue
                        if metric is None: continue
                        for cj, yr in years.items():
                            v = parse_number(rows[ri][cj] if cj < len(rows[ri]) else None)
                            if v is None: continue
                            v *= scale
                            if metric in COST_METRICS: v = abs(v)
                            bb = None
                            try: bb = [round(x, 1) for x in trows[ri].cells[cj]]
                            except Exception: pass
                            fid += 1
                            facts.append(Fact(fid, metric, yr, v, str(rows[ri][cj]).strip(), label.strip(), name, pno, ti, ri, cj, bb, scale, 1.0, "rules"))
                return len(facts) - n0
            def process_text() -> int:
                """Fallback for statements without ruled lines: parse aligned text lines. Lower confidence, no bounding box."""
                nonlocal fid
                n0 = len(facts); years: list[str] = []; scale = detect_scale(text[:700])
                for li, line in enumerate(text.splitlines()):
                    toks = line.split()
                    ys = [YEAR_RE.findall(t)[-1] for t in toks if YEAR_RE.fullmatch(t.replace("FY", "").replace("fy", ""))] if toks else []
                    if ys and all(parse_number(t) is None or YEAR_RE.fullmatch(t.replace("FY", "").replace("fy", "")) for t in toks) and len(ys) >= 1 and len(toks) <= len(ys) + 3:
                        years = ys; continue
                    if not years or not toks: continue
                    vals, i = [], len(toks)
                    while i > 0:
                        t = toks[i - 1]
                        if t.upper() in ("AED", "USD", "DHS"): i -= 1; continue
                        if re.search(r"\d", t) and parse_number(t) is not None: vals.append((i - 1, t)); i -= 1; continue
                        break
                    if len(vals) < len(years): continue
                    data = list(reversed(vals[:len(years)])); first = data[0][0]
                    j = first
                    while j > 0 and (toks[j - 1].upper() in ("AED", "USD", "DHS") or re.fullmatch(r"\d{1,2}", toks[j - 1])): j -= 1  # drop currency and note numbers
                    label = " ".join(toks[:j]); metric = map_label(label)
                    if metric is None:
                        if clean_label(label): unmapped.append({"label": label, "page": pno, "table": -1, "row": li})
                        continue
                    for k, (_, tv) in enumerate(data):
                        v = parse_number(tv)
                        if v is None: continue
                        v *= scale; v = abs(v) if metric in COST_METRICS else v; fid += 1
                        facts.append(Fact(fid, metric, years[k], v, tv, label, name, pno, -1, li, k, None, scale, 0.9, "text"))
                return len(facts) - n0
            if not process(page.find_tables()) and not process_text():
                if re.search(r"(19|20)\d{2}", text): warnings.append(f"page {pno}: no financial table recognised")
    if label_mapper and unmapped:  # optional LLM fallback for unknown labels
        m = label_mapper(sorted({u["label"] for u in unmapped}))
        warnings.append(f"{len(m)} unmapped labels sent to label_mapper; their facts are low confidence and need review")
    return {"facts": [asdict(f) for f in facts], "unmapped": unmapped, "warnings": warnings, "file": name}
