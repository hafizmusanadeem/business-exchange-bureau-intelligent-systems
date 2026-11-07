"""Tests for the hardened extractor (Module 5a): messy layouts, units, scans, OCR and the label mapper.
All documents are SYNTHETIC. No database or network needed. The real-OCR test is skipped when Tesseract is not installed."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.bxb import finance_extract as FE, finance_validate as FV

ST = getSampleStyleSheet()


def _tmp(name: str) -> str:
    return os.path.join(tempfile.mkdtemp(), name)


def _table(rows, grid=True):
    t = Table(rows)
    t.setStyle(TableStyle(([("GRID", (0, 0), (-1, -1), 0.5, colors.black)] if grid else []) + [("FONTSIZE", (0, 0), (-1, -1), 9)]))
    return t


def _build(path, flow):
    SimpleDocTemplate(path, pagesize=A4).build(flow)
    return path


def _by(out):
    return {(f["metric"], f["period"]): f for f in out["facts"]}


def messy_statement() -> str:
    """IFRS-style: title carries the period, a Note column, 'Dec 2025' headers, brackets for costs, section rows, 'Total equity and liabilities'."""
    hdr = ["", "Note", "31 Dec 2025", "31 Dec 2024"]
    income = [hdr,
              ["Revenue from contracts with customers", "4", "3,450,000", "2,880,000"],
              ["Cost of sales", "", "(1,449,000)", "(1,210,000)"],
              ["Gross profit/(loss)", "", "2,001,000", "1,670,000"],
              ["Other operating income", "", "15,000", "10,000"],
              ["Operating expenses", "", "(862,000)", "(720,000)"],
              ["Depreciation", "", "(69,000)", "(58,000)"],
              ["Operating profit", "", "1,085,000", "902,000"],
              ["Profit before taxation", "", "1,085,000", "902,000"],
              ["Profit/(loss) for the year", "", "976,500", "811,800"]]
    balance = [hdr,
               ["ASSETS", "", "", ""], ["Total assets", "", "3,000,000", "2,500,000"],
               ["EQUITY AND LIABILITIES", "", "", ""], ["Total equity", "", "1,800,000", "1,500,000"],
               ["Total liabilities", "", "1,200,000", "1,000,000"], ["Total equity and liabilities", "", "3,000,000", "2,500,000"]]
    return _build(_tmp("messy.pdf"), [Paragraph("Statement of profit or loss for the year ended 31 December 2025", ST["Title"]), _table(income),
                                      PageBreak(), Paragraph("Statement of financial position", ST["Title"]), _table(balance)])


def test_year_headers_in_many_formats():
    y = FE.year_of
    assert y("2025") == "2025" and y("Year ended 31 December 2025") == "2025" and y("31/12/2024") == "2024"
    assert y("Dec-25") == "2025" and y("FY25") == "2025" and y("FY2024") == "2024" and y("2025\nAED") == "2025"
    assert y("Notes") is None and y("Decrease 12") is None and y("1,234,000") is None and y("") is None


def test_real_world_label_traps():
    m = FE.map_label
    assert m("Profit before taxation") == "profit_before_tax"          # was read as tax
    assert m("Total equity and liabilities") == "total_equity_and_liabilities"   # was read as total equity
    assert m("Total liabilities and equity") == "total_equity_and_liabilities"
    assert m("Other operating income") is None and m("Other expenses") is None   # would duplicate operating profit / expenses
    assert m("Profit/(loss) for the year") == "net_profit" and m("Gross profit/(loss)") == "gross_profit"
    assert m("Revenue from contracts with customers") == "revenue" and m("Cash and bank balances") == "cash"
    assert m("Total shareholders' equity") == "total_equity" and m("Cash sales") is None and m("Customer deposits") is None


def test_messy_ifrs_statement():
    out = FE.extract_pdf(messy_statement()); f = _by(out)
    assert f[("revenue", "2025")]["value"] == 3_450_000 and f[("revenue", "2024")]["value"] == 2_880_000
    assert f[("cost_of_sales", "2025")]["value"] == 1_449_000           # brackets become a positive cost
    assert f[("net_profit", "2025")]["value"] == 976_500 and ("profit_before_tax", "2025") in f and ("tax", "2025") not in f
    assert f[("total_equity", "2025")]["value"] == 1_800_000            # not the 3,000,000 of "Total equity and liabilities"
    assert f[("total_equity_and_liabilities", "2025")]["value"] == 3_000_000
    labels = {u["label"] for u in out["unmapped"]}
    assert "Other operating income" in labels and not {"ASSETS", "EQUITY AND LIABILITIES"} & labels   # reported, but headings are not noise
    codes = {x["code"] for x in FV.validate(out["facts"])}
    assert not {"BALANCE_SHEET_MISMATCH", "GROSS_PROFIT_MISMATCH"} & codes


def test_unit_stated_once_is_carried_with_a_warning():
    p = _build(_tmp("units.pdf"), [Paragraph("Income statement (AED in thousands)", ST["Title"]), _table([["Item", "2025", "2024"], ["Revenue", "3,450", "2,880"]]),
                                   PageBreak(), Paragraph("Balance sheet", ST["Title"]), _table([["Item", "2025", "2024"], ["Total assets", "3,000", "2,500"]]),
                                   PageBreak(), Paragraph("Bank statement summary (AED)", ST["Title"]), _table([["Item", "2025", "2024"], ["Total credits", "3,480,000", "2,850,000"]])])
    out = FE.extract_pdf(p); f = _by(out)
    assert f[("revenue", "2025")]["value"] == 3_450_000
    assert f[("total_assets", "2025")]["value"] == 3_000_000 and any("page 2" in w and "unit" in w for w in out["warnings"])
    assert f[("bank_deposits", "2025")]["value"] == 3_480_000           # bank figures are never scaled by carry-over


def test_month_year_headers_without_ruled_lines():
    p = _build(_tmp("dec.pdf"), [Paragraph("Income statement", ST["Title"]), _table([["Item", "Dec-25", "Dec-24"], ["Net sales", "3,450,000", "2,880,000"],
                                                                                      ["Cost of goods sold", "1,449,000", "1,210,000"]], grid=False)])
    out = FE.extract_pdf(p); f = _by(out)
    assert f[("revenue", "2025")]["value"] == 3_450_000 and f[("cost_of_sales", "2024")]["value"] == 1_210_000
    assert all(x["mapped_by"] == "text" and x["confidence"] < 1 for x in out["facts"])


def test_year_only_in_the_title():
    p = _build(_tmp("title.pdf"), [Paragraph("Income statement for the year ended 31 December 2025", ST["Title"]), Spacer(1, 12),
                                   Paragraph("Revenue 3,450,000", ST["Normal"]), Paragraph("Cost of sales 1,449,000", ST["Normal"])])
    f = _by(FE.extract_pdf(p))
    assert f[("revenue", "2025")]["value"] == 3_450_000 and f[("cost_of_sales", "2025")]["value"] == 1_449_000


def _scan(path="scan.pdf") -> str:
    p = _tmp(path); c = canvas.Canvas(p, pagesize=A4); c.rect(60, 60, 200, 200, fill=1); c.save(); return p   # a page with no text layer


def test_scanned_page_uses_ocr_hook_and_wrapped_labels():
    ocr_text = ("Statement of profit or loss\nYear ended 31 December 2025 2024\nRevenue from contracts with\ncustomers 3,450,000 2,880,000\n"
                "Cost of sales (1,449,000) (1,210,000)\nProfit/(loss) for the year 976,500 811,800\n")
    out = FE.extract_pdf(_scan(), ocr=lambda page: ocr_text); f = _by(out)
    assert f[("revenue", "2025")]["value"] == 3_450_000 and f[("net_profit", "2024")]["value"] == 811_800
    assert all(x["mapped_by"] == "ocr" and x["confidence"] == FE.OCR_CONFIDENCE for x in out["facts"])
    assert any("OCR" in w and "page 1" in w for w in out["warnings"])


def test_scanned_page_without_ocr_warns_instead_of_crashing():
    def no_ocr(page): raise ImportError("pytesseract")
    out = FE.extract_pdf(_scan(), ocr=no_ocr)
    assert out["facts"] == [] and any("OCR is unavailable" in w for w in out["warnings"])


def _sundry_pdf():
    return _build(_tmp("sundry.pdf"), [_table([["Item", "2024", "2025"], ["Revenue", "100", "120"], ["Sundry write-offs", "5", "6"], ["Other operating income", "1", "2"]])])


def test_label_mapper_classifies_unknown_rows_with_low_confidence():
    seen = []
    def mapper(labels): seen.extend(labels); return {"Sundry write-offs": "depreciation", "Other operating income": "not_a_metric"}
    out = FE.extract_pdf(_sundry_pdf(), label_mapper=mapper); f = _by(out)
    assert sorted(seen) == ["Other operating income", "Sundry write-offs"]          # only labels are sent, never amounts
    d = f[("depreciation", "2025")]
    assert d["value"] == 6 and d["mapped_by"] == "llm" and d["confidence"] == FE.LLM_CONFIDENCE
    assert [u["label"] for u in out["unmapped"]] == ["Other operating income"]      # an invalid answer is ignored, not trusted
    assert any("label_mapper" in w for w in out["warnings"])


def test_failing_label_mapper_never_blocks_extraction():
    def boom(labels): raise TimeoutError()
    out = FE.extract_pdf(_sundry_pdf(), label_mapper=boom)
    assert ("revenue", "2025") in _by(out) and any("label_mapper failed" in w for w in out["warnings"])


def test_unreadable_pdf_text_is_reported_not_raised():
    p = _build(_tmp("prose.pdf"), [Paragraph("Dear buyer, in 2025 we grew. Thank you.", ST["Normal"])])
    out = FE.extract_pdf(p)
    assert out["facts"] == [] and any("no financial table recognised" in w for w in out["warnings"])


def test_real_ocr_on_an_image_only_pdf():
    """End to end with Tesseract on a rasterised statement. Skipped where Tesseract or pytesseract is missing."""
    try:
        import pytesseract  # noqa: F401
        import pdfplumber
    except ImportError:
        return
    if not shutil.which("tesseract"):
        return
    src = _build(_tmp("src.pdf"), [Paragraph("Income Statement (AED)", ST["Title"]),
                                   _table([["Item", "2024", "2025"], ["Revenue", "2,880,000", "3,450,000"], ["Cost of sales", "1,210,000", "1,449,000"],
                                           ["Gross profit", "1,670,000", "2,001,000"], ["Net profit", "802,800", "963,000"]])])
    with pdfplumber.open(src) as pdf:
        png = _tmp("scan.png"); pdf.pages[0].to_image(resolution=200).original.save(png)
    scan = _tmp("scan.pdf"); c = canvas.Canvas(scan, pagesize=A4); c.drawImage(png, 0, 0, width=A4[0], height=A4[1]); c.save()
    out = FE.extract_pdf(scan); f = _by(out)
    assert f[("revenue", "2025")]["value"] == 3_450_000 and f[("net_profit", "2024")]["value"] == 802_800
    assert f[("cost_of_sales", "2025")]["value"] == 1_449_000          # "Costofsales" (spaces dropped by OCR) is still recognised
    assert all(x["mapped_by"] == "ocr" for x in out["facts"])
