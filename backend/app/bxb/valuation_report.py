"""Module 8b: AI-drafted valuation report with a human review step.

WHY: a preliminary valuation is a 12 to 15 page report that takes days because people re-type statements into
spreadsheets and write the narrative. Extraction, validation, valuation maths and a verified narrative already exist
(Modules 5 and 6). This module joins them into a DRAFT that an analyst reviews instead of builds.

HUMAN IN THE LOOP: every draft starts as "pending_review". Only an analyst can approve it. A draft whose narrative
failed verification, or that has high-severity data flags and no reviewer note, cannot be approved.

All numbers come from code: extraction (pdfplumber), validation, DCF and multiples. The narrative may only restate
facts from the fact bank and every sentence is checked by grounding.verify_report. No LLM is used in this module.
ASSUMPTIONS (review hours) are placeholders to be replaced with a BXB time study."""
from __future__ import annotations

import io
import os
import random
import tempfile
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from xml.sax.saxutils import escape

try:
    from app.bxb import finance_extract as FE, finance_validate as FV, grounding as G, valuation as V
except ImportError:  # flat import when running tests without the template
    import finance_extract as FE, finance_validate as FV, grounding as G, valuation as V

ASSUMPTIONS = {
    "manual_hours_per_report": 12.0,
    "review_hours_light": 1.5,
    "review_hours_full": 4.0,
    "review_hours_escalated": 6.0,
    "note": "Placeholder effort figures for the demo. Replace with a measured BXB analyst time study.",
}
METHOD_PHRASE = {
    "reported": "as reported in the statements",
    "operating_profit + depreciation": "derived as operating profit plus depreciation",
    "gross_profit - operating_expenses": "derived approximately as gross profit less operating expenses",
    "revenue - total_expenses": "derived approximately as revenue less total expenses",
}


def _m(x: float) -> str:
    """AED text the verifier can match: 1 decimal in millions, whole thousands below 1M."""
    return f"{x / 1e6:.1f}M" if abs(x) >= 1e6 else f"{x / 1e3:.0f}K"


# ----------------------------------------------------------------------------------------------- fact bank + text
def _bank(sector: str, latest: str | None, e: dict | None, val: dict, flags: list[dict], quality: int,
          asking: float | None, hist_periods: list[str]) -> tuple[list[dict], list[str]]:
    facts: list[dict] = []
    sents: list[str] = []

    def add(type_: str, values: dict, periods: list[str] | None = None) -> str:
        fid = f"F{len(facts) + 1}"
        facts.append({"id": fid, "type": type_, "entity": sector, "direction": None, "values": values,
                      "labels": [], "periods": periods or []})
        return fid

    if val["status"] != "ok":
        fid = add("ebitda_status", {})
        sents.append(f"No EBITDA-based valuation is produced for the {sector} business: EBITDA is missing or not positive. [{fid}]")
    else:
        fid = add("ebitda", {"ebitda_aed": e["value"]}, [latest])
        sents.append(f"Latest EBITDA ({latest}) is AED {_m(e['value'])}, {METHOD_PHRASE.get(e['method'], 'derived from the statements')}. [{fid}]")
        lo, hi = val["range_ev"]; base = val["scenarios"]["base"]["enterprise_value"]
        fid = add("valuation_range", {"range_low_aed": lo, "range_high_aed": hi, "base_aed": base})
        sents.append(f"The preliminary enterprise value range for the {sector} business is AED {_m(lo)} to AED {_m(hi)}, with a base case of AED {_m(base)}. [{fid}]")
        if asking and "asking_vs_range" in val:
            av = val["asking_vs_range"]; pos = av["position"].replace(" range", " the")
            fid = add("asking", {"asking_aed": asking, "asking_to_base_pct": av["asking_to_base_pct"]})
            sents.append(f"The asking price of AED {_m(asking)} sits {pos} range, at {av['asking_to_base_pct']}% of the base case. [{fid}]")
        fid = add("quality", {"quality_score": quality})
        sents.append(f"The data quality score is {quality} and valuation confidence is {val['confidence']}. [{fid}]")
        nh, nm = sum(f["severity"] == "high" for f in flags), sum(f["severity"] == "medium" for f in flags)
        fid = add("flags", {"n_high": nh, "n_medium": nm})
        sents.append(f"{nh} high-severity and {nm} medium-severity data flags were raised. [{fid}]")
        m = val["multiples"]
        fid = add("assumptions", {"multiple_conservative": m["conservative"], "multiple_base": m["base"], "multiple_optimistic": m["optimistic"]})
        sents.append(f"Multiples for the {sector} business are placeholders at {m['conservative']:.1f}x, {m['base']:.1f}x and {m['optimistic']:.1f}x EBITDA, not transaction evidence. [{fid}]")
        g = val.get("historical_ebitda_cagr")
        if g is not None and len(hist_periods) >= 2:
            fid = add("history", {"ebitda_cagr_pct": round(abs(g) * 100, 1)}, [hist_periods[0], hist_periods[-1]])
            verb = "expanded" if g >= 0 else "contracted"
            sents.append(f"Historical EBITDA {verb} at {abs(g) * 100:.1f}% a year between {hist_periods[0]} and {hist_periods[-1]}. [{fid}]")
    return facts, sents


def review_plan(flags: list[dict], quality: int, val: dict) -> dict:
    high = [f for f in flags if f["severity"] == "high"]
    med = [f for f in flags if f["severity"] == "medium"]
    light = val["status"] == "ok" and not high and not med and quality >= 90 and val.get("confidence") == "preliminary"
    tier = "light" if light else "full"
    hours = ASSUMPTIONS["review_hours_escalated"] if high else ASSUMPTIONS[f"review_hours_{tier}"]
    items = [f"Resolve {f['code']}: {f['message']}" for f in high + med]
    items += ["Confirm EBITDA add-backs (owner salary, one-off items) with the seller.",
              "Replace placeholder multiples with comparable closed deals before sending to a client.",
              "Check the seller's trade licence and ownership share."]
    manual = ASSUMPTIONS["manual_hours_per_report"]
    return {"tier": tier, "escalate": bool(high), "estimated_review_hours": hours,
            "estimated_manual_hours": manual, "estimated_hours_saved": round(manual - hours, 1),
            "checklist": items, "assumptions": ASSUMPTIONS}


# ----------------------------------------------------------------------------------------------------- the draft
def build_draft(extraction: dict, sector: str, asking: float | None = None, sample: str | None = None, owner: str | None = None) -> dict:
    facts = extraction["facts"]
    if not facts:
        raise ValueError("No financial tables were recognised in this PDF.")
    idx = FV.index(facts); flags = FV.validate(facts); quality = FV.quality_score(flags)
    periods = sorted({f["period"] for f in facts})
    ebitdas = {p: FV.derive_ebitda(idx, p) for p in periods}
    ebitdas = {p: e for p, e in ebitdas.items() if e}
    latest = max(ebitdas) if ebitdas else None
    e = ebitdas.get(latest) if latest else None
    hist = {p: x["value"] for p, x in ebitdas.items()}
    debt = FV.best(idx, "debt", latest) if latest else None
    cash = FV.best(idx, "cash", latest) if latest else None
    net_debt = (debt["value"] if debt else 0) - (cash["value"] if cash else 0) if (debt or cash) else None
    val = V.valuate(e["value"] if e else None, sector, hist, asking, net_debt, quality, flags, bool(e and e["approximate"]))
    bank, sents = _bank(sector, latest, e, val, flags, quality, asking, sorted(hist))
    verification = G.verify_report(sents, bank)
    return {
        "id": uuid.uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "pending_review", "owner": owner, "sample": sample,
        "sector": sector, "asking_price": asking, "latest_period": latest,
        "ebitda": e, "data_quality_score": quality, "flags": flags, "valuation": val,
        "report": {"sentences": sents, "fact_bank": bank, "verification": verification},
        "review": review_plan(flags, quality, val), "decision": None,
        "extraction": {"facts": facts, "unmapped": extraction.get("unmapped", []), "warnings": extraction.get("warnings", []), "file": extraction.get("file")},
    }


# ----------------------------------------------------------------------------------------------- review workflow
class DraftStore:
    """In-memory store for the demo (bounded). Production should persist drafts and reviews in the database."""

    def __init__(self, cap: int = 200):
        self._d: OrderedDict[str, dict] = OrderedDict(); self._cap = cap; self._lock = threading.Lock()

    def put(self, draft: dict) -> dict:
        with self._lock:
            self._d[draft["id"]] = draft
            while len(self._d) > self._cap:
                self._d.popitem(last=False)
        return draft

    def get(self, draft_id: str) -> dict | None:
        with self._lock:
            return self._d.get(draft_id)

    def review(self, draft_id: str, decision: str, reviewer: str, note: str = "") -> dict:
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be 'approve' or 'reject'")
        if not reviewer.strip():
            raise ValueError("reviewer name is required")
        with self._lock:
            d = self._d.get(draft_id)
            if d is None:
                raise KeyError(draft_id)
            if d["status"] != "pending_review":
                raise ValueError(f"draft is already {d['status']}")
            if decision == "approve":
                if not d["report"]["verification"]["ok"]:
                    raise ValueError("narrative failed verification and cannot be approved")
                if d["review"]["escalate"] and not note.strip():
                    raise ValueError("a reviewer note is required to approve a draft with high-severity flags")
            d["status"] = "approved" if decision == "approve" else "rejected"
            d["decision"] = {"decision": decision, "reviewer": reviewer.strip()[:80], "note": note.strip()[:1000],
                             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            return d


STORE = DraftStore()


# ----------------------------------------------------------------------------------------------------------- PDF
def render_pdf(d: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet(); P = lambda t, s="BodyText": Paragraph(escape(str(t)), st[s])
    val = d["valuation"]; dec = d["decision"]
    banner = {"pending_review": "AI-DRAFTED - PENDING ANALYST REVIEW", "approved": "APPROVED BY ANALYST", "rejected": "REJECTED BY ANALYST"}[d["status"]]
    story = [P("Preliminary Valuation Report", "Title"), P(banner, "Heading2")]
    if dec:
        story.append(P(f"Reviewer: {dec['reviewer']} on {dec['at']}. Note: {dec['note'] or 'none'}"))
    if d.get("sample"):
        story.append(P(f"SYNTHETIC DEMO DOCUMENT ({d['sample']}). Not a real business."))
    story += [Spacer(1, 8), P(f"Sector: {d['sector']}    Latest period: {d['latest_period'] or 'n/a'}    Data quality score: {d['data_quality_score']}")]
    if val["status"] == "ok":
        rows = [["Scenario", "Multiple", "EV (multiple)", "EV (DCF)", "Enterprise value", "Discount rate"]]
        for name, s in val["scenarios"].items():
            a = s["assumptions"]
            rows.append([name, f"{a['multiple']:.1f}x", f"{s['ev_multiple']:,}", f"{s['ev_dcf']:,}", f"{s['enterprise_value']:,}", f"{a['discount_rate']:.0%}"])
        t = Table(rows, hAlign="LEFT"); t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
                                                              ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
        story += [Spacer(1, 8), P("Valuation scenarios (AED)", "Heading3"), t]
    story += [Spacer(1, 8), P("Narrative (every sentence verified against the fact bank)", "Heading3")]
    story += [P(G.CITE.sub("", s).replace("  ", " ").strip()) for s in d["report"]["sentences"]]
    if d["flags"]:
        story += [Spacer(1, 8), P("Data flags (prompts for professional review)", "Heading3")]
        story += [P(f"[{f['severity'].upper()}] {f['code']}: {f['message']}") for f in d["flags"]]
    facts = d["extraction"]["facts"][:60]
    rows = [["Metric", "Period", "Value", "File", "Page", "Confidence"]] + [[f["metric"], f["period"], f"{f['value']:,.0f}", f["file"], f["page"], f"{f['confidence']:.2f}"] for f in facts]
    t = Table(rows, hAlign="LEFT", repeatRows=1); t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7)]))
    story += [Spacer(1, 8), P("Source figures (provenance)", "Heading3"), t]
    if len(d["extraction"]["facts"]) > 60:
        story.append(P(f"Showing 60 of {len(d['extraction']['facts'])} extracted figures."))
    story += [Spacer(1, 10), P("This is a preliminary, machine-assisted estimate. It is not a professional valuation. Multiples and rates are placeholders, "
                                "not transaction evidence. Asking prices are not sale prices.", "Italic")]
    buf = io.BytesIO(); SimpleDocTemplate(buf, pagesize=A4, title="Preliminary Valuation Report").build(story)
    return buf.getvalue()


# ------------------------------------------------------------------------------------------- synthetic samples/eval
def sample_pdf(kind: str, seed: int = 7, directory: str | None = None) -> tuple[str, int]:
    """Synthetic statements. 'fraud' plants a revenue/bank gap and an inflated gross profit. Returns (path, asking price)."""
    if kind not in ("clean", "fraud"):
        raise ValueError("kind must be 'clean' or 'fraud'")
    try:
        from app.bxb import finance_synth as FS
    except ImportError:
        import finance_synth as FS
    t = FS.make_truth(random.Random(seed))
    if kind == "fraud":
        for y in t:
            t[y]["bank_deposits"] = round(t[y]["revenue"] * 0.58)
        t["2025"]["gross_profit"] = round(t["2025"]["gross_profit"] * 1.15)
    path = os.path.join(directory or tempfile.mkdtemp(), f"sample_{kind}_{seed}.pdf")
    FS.build_pdf(path, t, "A", bank=True)
    return path, int(round(3.5 * (t["2025"]["operating_profit"] + t["2025"]["depreciation"]), -3))


def draft_sample(kind: str, seed: int = 7, owner: str | None = None) -> dict:
    d = tempfile.mkdtemp()
    path, asking = sample_pdf(kind, seed, d)
    try:
        return build_draft(FE.extract_pdf(path, file_name=f"sample_{kind}.pdf"), "Food & Beverage", asking, sample=kind, owner=owner)
    finally:
        try:
            os.unlink(path); os.rmdir(d)
        except OSError:
            pass


def evaluate_samples(n: int = 6, seed: int = 1) -> dict:
    """End to end on SYNTHETIC PDFs: false alarms on clean files, detection of planted problems, verifier pass rate."""
    clean_fa = fraud_hit = verified = 0; saved = []
    for i in range(n):
        c = draft_sample("clean", seed * 100 + i); f = draft_sample("fraud", seed * 100 + i)
        clean_fa += any(x["severity"] in ("high", "medium") for x in c["flags"])
        fraud_hit += any(x["code"] in ("REVENUE_BANK_GAP", "GROSS_PROFIT_MISMATCH") and x["severity"] == "high" for x in f["flags"])
        verified += c["report"]["verification"]["ok"] + f["report"]["verification"]["ok"]
        saved += [c["review"]["estimated_hours_saved"], f["review"]["estimated_hours_saved"]]
    return {"documents_per_kind": n, "clean_docs_with_false_alarm": f"{clean_fa}/{n}", "planted_problems_flagged_high": f"{fraud_hit}/{n}",
            "narratives_passing_verifier": f"{verified}/{2 * n}", "mean_estimated_hours_saved": round(sum(saved) / len(saved), 1),
            "note": "Synthetic, cleanly ruled tables. Hours saved use placeholder assumptions, not a BXB time study."}
