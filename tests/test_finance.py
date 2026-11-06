"""Module tests (no DB required where possible)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import os
import random
import tempfile

from app.bxb import finance_extract as FE, finance_validate as FV, valuation as V, finance_synth as FS

def test_parse_number_variants():
    p = FE.parse_number
    assert p("1,234") == 1234 and p("(1,234)") == -1234 and p("AED 4,000,000") == 4_000_000 and p("-5") == -5
    assert p("1.2M") == 1_200_000 and p("350k") == 350_000 and p("-") is None and p("12%") is None and p("abc") is None and p(None) is None

def test_scale_detection():
    assert FE.detect_scale("Income Statement - AED '000") == 1e3 and FE.detect_scale("in millions of AED") == 1e6 and FE.detect_scale("Income (AED)") == 1.0

def test_label_mapping_and_false_friends():
    m = FE.map_label
    assert m("Turnover") == "revenue" and m("Direct costs") == "cost_of_sales" and m("Profit for the year (Note 4)") == "net_profit"
    assert m("Total shareholders' equity") == "total_equity" and m("Administrative expenses") == "operating_expenses"
    assert m("Debit card sales") is None and m("Cash sales") is None and m("Customer deposits") is None  # must not hijack real metrics

def test_pdf_extraction_has_provenance():
    rng = random.Random(0); t = FS.make_truth(rng); p = os.path.join(tempfile.mkdtemp(), "a.pdf"); FS.build_pdf(p, t, "C", bank=True)
    out = FE.extract_pdf(p, file_name="seller.pdf"); f = next(x for x in out["facts"] if x["metric"] == "revenue" and x["period"] == "2025")
    assert f["file"] == "seller.pdf" and f["page"] == 1 and f["raw"].startswith("AED") and f["bbox"] and abs(f["value"] - t["2025"]["revenue"]) < 1
    bs = next(x for x in out["facts"] if x["metric"] == "total_assets"); assert bs["page"] == 2   # multi-page

def test_extraction_accuracy_all_layouts():
    r = FS.evaluate(n_per_layout=3, seed=11)
    assert r["overall_field_accuracy"] >= 0.99 and r["validator"]["clean_docs_with_false_alarm"].startswith("0/")
    assert all(v >= 0.9 for v in r["validator"]["detection_rate"].values())

def F(i, m, p, v, f="x.pdf"): return dict(id=i, metric=m, period=p, value=v, file=f, page=1, confidence=1.0)

def test_ebitda_derivation_methods():
    idx = FV.index([F(1, "operating_profit", "2025", 700), F(2, "depreciation", "2025", 100)])
    assert FV.derive_ebitda(idx, "2025")["value"] == 800
    idx = FV.index([F(1, "revenue", "2025", 4_000_000), F(2, "total_expenses", "2025", 3_200_000)])
    e = FV.derive_ebitda(idx, "2025"); assert e["value"] == 800_000 and e["approximate"] and "note" in e   # the document's worked example

def test_bank_gap_matches_document_example():
    flags = FV.validate([F(1, "revenue", "2025", 4_000_000), F(2, "bank_deposits", "2025", 2_900_000, "bank.pdf")])
    g = next(f for f in flags if f["code"] == "REVENUE_BANK_GAP")
    assert g["severity"] == "high" and g["evidence"] == [1, 2] and "professional review" in g["message"] and "fraud" not in g["message"].lower()

def test_no_flags_when_consistent():
    facts = [F(1, "revenue", "2024", 100), F(2, "cost_of_sales", "2024", 40), F(3, "gross_profit", "2024", 60), F(4, "bank_deposits", "2024", 98)]
    assert [f for f in FV.validate(facts) if f["severity"] in ("high", "medium")] == []

def test_missing_period_and_conflict():
    flags = {f["code"] for f in FV.validate([F(1, "revenue", "2023", 1), F(2, "revenue", "2025", 2), F(3, "revenue", "2025", 3, "other.pdf")])}
    assert {"MISSING_PERIOD", "CROSS_DOC_CONFLICT"} <= flags

def test_dcf_matches_hand_calculation():
    # flat case: g0 = tg = 0, conv 1: EV = E * (annuity 5y + terminal) ; check against closed form
    r = 0.10; ev = V.dcf(100.0, 0.0, r, 0.0, 1.0, 5)
    expected = sum(100 / (1 + r) ** t for t in range(1, 6)) + (100 / r) / (1 + r) ** 5
    assert abs(ev - expected) < 1e-9 and abs(ev - 1000) < 1e-6
    try: V.dcf(100, 0, 0.02, 0.03, 1.0); assert False
    except ValueError: pass

def test_valuation_scenarios_ordered_and_guarded():
    v = V.valuate(800_000, "Food & Beverage", {"2023": 400_000, "2025": 800_000}, asking=3_500_000)
    s = v["scenarios"]; assert s["conservative"]["enterprise_value"] < s["base"]["enterprise_value"] < s["optimistic"]["enterprise_value"]
    assert v["multiples_are_placeholders"] and v["asking_vs_range"]["position"] in ("below range", "within range", "above range")
    assert V.valuate(-5, "Retail")["status"] == "not_meaningful" and V.valuate(None, "Retail")["status"] == "not_meaningful"

def test_high_flag_lowers_confidence():
    flags = FV.validate([F(1, "revenue", "2025", 4_000_000), F(2, "bank_deposits", "2025", 2_000_000, "b.pdf")])
    v = V.valuate(800_000, "Retail", None, None, None, FV.quality_score(flags), flags)
    assert v["confidence"] == "low" and any("high-severity" in w for w in v["warnings"])

def test_text_fallback_without_ruled_lines():
    rng = random.Random(4); t = FS.make_truth(rng); p = os.path.join(tempfile.mkdtemp(), "ng.pdf"); FS.build_pdf(p, t, "C", grid=False)
    out = FE.extract_pdf(p); o, n = FS.score(t, out["facts"], skip=("bank_deposits",))
    assert o / n >= 0.95 and all(f["mapped_by"] == "text" and f["confidence"] < 1 and f["bbox"] is None for f in out["facts"])

def test_unknown_labels_are_reported_not_guessed():
    rng = random.Random(1); t = FS.make_truth(rng); FS.NAMES["A"]["depreciation"] = "Sundry write-offs"
    try:
        p = os.path.join(tempfile.mkdtemp(), "u.pdf"); FS.build_pdf(p, t, "A"); out = FE.extract_pdf(p)
    finally: FS.NAMES["A"]["depreciation"] = "Depreciation"
    assert any("sundry" in u["label"].lower() for u in out["unmapped"]) and not any(f["metric"] == "depreciation" for f in out["facts"])
