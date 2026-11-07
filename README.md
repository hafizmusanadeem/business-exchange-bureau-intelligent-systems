# BXB Pulse – Modules 1–6 (MVP)

Clean, template-ready implementation of Steps 1–6 of the BXB Pulse development plan.

## Modules

| # | Name | Key files | API prefix |
|---|------|-----------|------------|
| 1 | Foundation | models, synthetic, seed | `/bxb` |
| 2 | Investor Sentiment | sentiment | `/bxb/sentiment` |
| 3 | Sale Trends & Forecast | trends, forecast | `/bxb/trends` |
| 4 | Investor Matching | matching, metrics, eval_matching | `/bxb/matching` |
| 5 | Financial Intelligence | finance_extract, finance_validate, valuation, finance_synth | `/bxb/financials` |
| 6 | Grounded AI Reports | report_facts, grounding, report_writer, eval_grounding | `/bxb/reports` |
| 8 | AI cost reduction | valuation_report, feasibility, listing_screen, verifier_demo, scoreboard | `/bxb/ai` |

## Quick start

See [`docs/MODULE1_INTEGRATION.md`](docs/MODULE1_INTEGRATION.md).

## Design highlights

- **Qualified demand only** – views never count; demand unit = unique (investor, listing).
- **Asking price ≠ sale price** – every market response says so explicitly.
- **Honest forecasts** – richer model only if it beats baseline by ≥ 5% MAE.
- **Hard filters before ranking** – model cannot override sector/budget/EBITDA.
- **Financial facts with full provenance** – file, page, table, row, col, bbox; unknown labels listed as unmapped, never guessed.
- **Grounded reports** – every number must cite a fact; verifier is plain code; LLM path falls back to template on any failure.

## Dependencies

- Modules 1–3: stdlib only for metrics
- Module 4: `scikit-learn`, `numpy`, `joblib`
- Module 5: `pdfplumber` (+ `python-multipart` already in the template)
- Module 6 LLM path (optional): Anthropic API key + `BXB_LLM_ENABLED=1`

## Module 8: AI cost reduction (demo)

Aimed at steps BXB staffs by hand today. Pages: `/valuation.html` and `/ai-lab.html`. All data synthetic.

- **AI-drafted valuation** – PDF in, extracted figures with provenance, validator flags, valuation scenarios, a verified
  narrative, an analyst review screen and a PDF out. Nothing is approved without a person.
- **Sale-service feasibility** – counts investors passing the hard filters, so a "minimum N matches" guarantee is only
  promised when it can be kept.
- **Listing screening** – explainable rules plus an outlier model produce a moderation queue; humans decide.
- **Verifier under attack** – bad sentences an LLM might write are rejected with exact reasons.
- **Scoreboard** – `python -m app.bxb.scoreboard` writes every offline evaluation to JSON.

## Stretch (not included)

Module 7 (Deal workspace) remains optional per the plan.
