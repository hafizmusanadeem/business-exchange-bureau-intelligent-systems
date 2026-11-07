"""Module 8e: evaluation scoreboard. One place that runs every offline evaluation and stores the result as JSON so a
page can show it instantly. Each section is isolated: if one evaluator fails, the others still report.
ALL FIGURES ARE ON SYNTHETIC DATA and the output says so.

    python -m app.bxb.scoreboard        # recompute and write the JSON file"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


def default_path() -> Path:
    return Path(os.getenv("BXB_SCOREBOARD_PATH", "scoreboard.json"))


def collect(evaluators: dict[str, Callable[[], dict]]) -> dict:
    sections = {}
    for name, fn in evaluators.items():
        t0 = time.perf_counter()
        try:
            sections[name] = {"ok": True, "seconds": round(time.perf_counter() - t0, 2), "result": fn()}
            sections[name]["seconds"] = round(time.perf_counter() - t0, 2)
        except Exception as e:  # one broken evaluator must not hide the rest
            sections[name] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "synthetic": True,
            "disclaimer": "All figures are measured on synthetic data. They show the pipeline works, not how it performs on BXB data.",
            "sections": sections}


def save(data: dict, path: Path | str | None = None) -> Path:
    p = Path(path) if path else default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)
    return p


def load(path: Path | str | None = None) -> dict | None:
    p = Path(path) if path else default_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def default_evaluators() -> dict[str, Callable[[], dict]]:
    """Imports are lazy so the module loads without scikit-learn or reportlab."""
    def extraction():
        from app.bxb import finance_synth as FS
        return FS.evaluate(n_per_layout=4, seed=1)

    def grounding():
        from app.bxb import eval_grounding as EG
        return EG.evaluate(seeds=(1,))

    def matching():
        from app.bxb import eval_matching as EM
        return EM.evaluate(seed=7, k_boot=200)

    def screening():
        from app.bxb import listing_screen as LS
        return LS.evaluate()

    def drafts():
        from app.bxb import valuation_report as VR
        return VR.evaluate_samples(n=4)

    def attacks():
        from app.bxb import verifier_demo as VD
        return VD.summary()

    return {"extraction_and_validation": extraction, "grounded_reports": grounding, "investor_matching": matching,
            "listing_screening": screening, "valuation_drafts": drafts, "verifier_attacks": attacks}


def refresh(path: Path | str | None = None) -> dict:
    data = collect(default_evaluators()); save(data, path); return data


if __name__ == "__main__":
    print(json.dumps(refresh(), indent=2))
