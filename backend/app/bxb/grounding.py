"""Module 6b: the VERIFIER. A report sentence passes only if
  1. every number in it matches a value of a fact it cites (after rounding to the digits shown),
  2. any sentence with a number cites at least one fact, and cited ids exist,
  3. it names no sector that its cited facts do not cover,
  4. its direction words do not contradict the cited facts,
  5. it makes no causal claim and no unsupported prediction.
Pure code, no LLM. Limits: it checks numbers, entities, direction and causal wording; it cannot judge whether a
true statement is well chosen or complete. Keep a human reviewer for published reports."""
from __future__ import annotations
import re

CITE = re.compile(r"\[(F\d+)\]")
QUARTER = re.compile(r"\b(?:19|20)\d{2}-Q[1-4]\b|\bQ[1-4]\b")
NUM = re.compile(r"(?<![\w.])(AED\s*)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?\s?(M\b|K\b|m\b|k\b|%|pts?\b|points?\b)?")
UP = re.compile(r"\b(increas\w*|ris(e|es|en|ing)|rose|grew|grow\w*|gain\w*|higher|climb\w*|surg\w*)\b", re.I)
DOWN = re.compile(r"\b(decreas\w*|fell|fall\w*|declin\w*|drop\w*|lower|shrank|shrink\w*|slump\w*)\b", re.I)
CAUSAL = re.compile(r"\b(because|due to|driven by|as a result of|caused by|thanks to|owing to|attributable to|reflect(s|ing)? (growing|rising|falling|strong|weak)|amid)\b", re.I)
LINKY = re.compile(r"(https?://|www\.|\b\S+@\S+\.\w+|ignore (all |previous |the )|disregard|click here|visit )", re.I)
PREDICT = re.compile(r"\b(will|expected to|likely to|guarantee\w*|certain(ly)?)\b", re.I)


def numbers(text: str) -> list[tuple[float, int, str]]:
    """[(mantissa, decimals, unit)] for every number in text (citations and quarter labels removed)."""
    t = QUARTER.sub(" ", CITE.sub(" ", text)); out = []
    for m in NUM.finditer(t):
        aed, whole, dec, unit = m.group(1), m.group(2), m.group(3) or "", (m.group(4) or "").strip().lower()
        u = "m" if unit == "m" else "k" if unit == "k" else "%" if unit == "%" else "pts" if unit.startswith("p") else ""
        out.append((float(whole.replace(",", "") + ("." + dec if dec else "")), len(dec), u, "money" if (aed or u in ("m", "k")) else "pct" if u == "%" else "pts" if u == "pts" else "count"))
    return out


def kind_of(name: str) -> str:
    return "pct" if name.endswith("_pct") else "pts" if name.endswith("_pts") else "money" if name.endswith("_aed") else "count"


def allowed_values(fact: dict) -> list[tuple[float, str]]:
    """[(value, kind)]. A number must match a value of the SAME kind (percent, points, money, count), so a
    fabricated '12%' cannot hide behind an unrelated '12 months'."""
    vals = [(float(v), kind_of(k)) for k, v in fact["values"].items() if isinstance(v, (int, float))]
    for lab in fact.get("labels", []):
        for mant, _, unit, kind in numbers(lab): vals.append((mant * {"m": 1e6, "k": 1e3}.get(unit, 1), "money" if kind == "money" else kind))
    for per in fact.get("periods", []):
        for y in re.findall(r"(?:19|20)\d{2}", per): vals.append((float(y), "count"))
    return vals


def _ok(tok, allowed: list[tuple[float, str]]) -> bool:
    mant, d, unit, kind = tok
    for a, k in allowed:
        if k != kind: continue
        cand = abs(a) / 1e6 if unit == "m" else abs(a) / 1e3 if unit == "k" else abs(a)
        if kind != "money":   # percentages, points and counts must be quoted at the stored precision, so 11.6% cannot pass as "12%"
            frac = f"{cand:.6f}".rstrip("0").split(".")[1] if "." in f"{cand:.6f}".rstrip("0") else ""
            if d < len(frac): continue
        if round(cand, d) == mant: return True
    return False


def verify_sentence(text: str, bank: dict[str, dict], sectors: set[str]) -> dict:
    cites = CITE.findall(text); v = []
    unknown = [c for c in cites if c not in bank]
    if unknown: v.append(f"cites unknown fact(s) {', '.join(unknown)}")
    used = [bank[c] for c in cites if c in bank]; nums = numbers(text)
    if not used and text.strip() not in BOILERPLATE: v.append("cites no fact (every sentence must be grounded)")
    allowed = [x for f in used for x in allowed_values(f)]
    for tok in nums:
        if used and not _ok(tok, allowed): v.append(f"number {tok[0]:g}{tok[2] and ' ' + tok[2]} ({tok[3]}) is not supported by the cited facts")
    covered = {f["entity"] for f in used if f.get("entity")}
    for s in sectors:
        if s.lower() in text.lower() and s not in covered: v.append(f"mentions '{s}' but no cited fact covers it")
    dirs = {f["direction"] for f in used if f.get("direction")}
    if UP.search(text) and dirs and not (dirs & {"increasing"}) and ({"decreasing", "stable"} & dirs): v.append("direction words say up but cited facts say otherwise")
    if DOWN.search(text) and dirs and not (dirs & {"decreasing"}) and ({"increasing", "stable"} & dirs): v.append("direction words say down but cited facts say otherwise")
    if (UP.search(text) or DOWN.search(text)) and used and not dirs and not any(f["type"] in ("forecast",) for f in used): v.append("direction words used but cited facts carry no direction")
    if used and not nums and not covered and text.strip() not in BOILERPLATE: v.append("states nothing checkable: no number and no covered entity")
    if LINKY.search(text): v.append("contains a link or instruction-like text")
    if CAUSAL.search(text): v.append("unsupported causal claim")
    if PREDICT.search(text) and not any(f["type"] == "forecast" for f in used): v.append("prediction not backed by a forecast fact")
    return {"text": CITE.sub("", text).replace("  ", " ").strip(), "raw": text, "cites": cites, "ok": not v, "violations": v}


def verify_report(sentences: list[str], facts: list[dict]) -> dict:
    bank = {f["id"]: f for f in facts}; sectors = {f["entity"] for f in facts if f.get("entity")} | _ALL_SECTORS
    res = [verify_sentence(s, bank, sectors) for s in sentences]
    return {"ok": all(r["ok"] for r in res), "sentences": res, "failed": sum(not r["ok"] for r in res)}


BOILERPLATE = {"Gaps between demand and supply are prompts to investigate, not proof of unmet demand."}
_ALL_SECTORS = {"Food & Beverage", "Healthcare", "Beauty", "Information Technology", "Commercial Services", "Retail", "Logistics"}
