"""Measures the verifier: detection of planted hallucinations, false alarms on clean text, and the
retry + fallback loop with simulated LLMs. Run:  python -m app.bxb.eval_grounding   (SYNTHETIC data)"""
from __future__ import annotations
import json, random, re
from datetime import date
try:
    from app.bxb import grounding as G, report_facts as RF, report_writer as W
    from app.bxb.synthetic import generate
except ImportError:
    import grounding as G, report_facts as RF, report_writer as W
    from synthetic import generate

SECT = sorted(G._ALL_SECTORS)
def num_swap(s, rng):
    m = next(G.NUM.finditer(G.CITE.sub("", s)), None)
    if not m: return None
    txt = m.group(0); core = re.search(r"\d[\d,]*(\.\d+)?", txt).group(0); dec = len(core.split(".")[1]) if "." in core else 0
    new = f"{float(core.replace(',', '')) * 1.37 + 3:,.{dec}f}"; return s.replace(core, new, 1)
def dir_flip(s, rng):
    for a, b in (("rose", "fell"), ("fell", "rose"), ("a gain", "a drop"), ("a drop", "a gain"), ("higher", "lower"), ("lower", "higher")):
        if a in s: return s.replace(a, b, 1)
def causal(s, rng): return re.sub(r"( \[F\d+\])", " because of stronger consumer confidence\\1", s, count=1) if "[F" in s else None
def uncited(s, rng): return G.CITE.sub("", s).strip() if re.search(r"\d", s) else None
def wrong_sector(s, rng):
    for x in SECT:
        if x in s: return s.replace(x, rng.choice([y for y in SECT if y != x]), 1)
def fabricated(s, rng): return s + " 12% of investors are from Germany. [F1]"
MUT = {"number_swap": num_swap, "direction_flip": dir_flip, "causal_claim": causal, "uncited_number": uncited, "wrong_sector": wrong_sector, "fabricated_stat": fabricated}


def facts_for(seed):
    d = generate(seed=seed); inv = {i["id"]: i for i in d["investors"]}
    return RF.collect_facts(d["events"], d["listings"], inv, "2023-Q4", "2026-Q2", date(2026, 6, 30))


def simulated_llm(facts, p_bad: float, seed: int, decay: float = 0.5):
    rng = random.Random(seed); clean = [s for ss in W.template_report(facts).values() for s in ss if s not in G.BOILERPLATE]; state = {"p": p_bad}
    def call(system, user):
        out = []
        for s in clean:
            if rng.random() < state["p"]:
                m = rng.choice(list(MUT.values())); out.append(m(s, rng) or s)
            else: out.append(s)
        state["p"] *= decay; return "\n".join(out)
    return call


def evaluate(seeds=(1, 2, 3)) -> dict:
    rng = random.Random(0); clean_n = clean_bad = 0; det = {k: [0, 0] for k in MUT}
    for sd in seeds:
        facts = facts_for(sd); flat = [s for ss in W.template_report(facts).values() for s in ss]; v = G.verify_report(flat, facts)
        clean_n += len(flat); clean_bad += v["failed"]; bank = {f["id"]: f for f in facts}; secs = {f["entity"] for f in facts if f["entity"]} | G._ALL_SECTORS
        for s in flat:
            if s in G.BOILERPLATE: continue
            for k, fn in MUT.items():
                bad = fn(s, rng)
                if bad is None or bad == s: continue
                det[k][1] += 1; det[k][0] += not G.verify_sentence(bad, bank, secs)["ok"]
    loop = {}
    facts = facts_for(1)
    for name, p, decay in (("careless_llm", 0.3, 0.5), ("very_bad_llm", 0.9, 1.0), ("always_hallucinates", 1.0, 1.0)):
        r = W.generate(facts, simulated_llm(facts, p, 5, decay)); loop[name] = {"final_report_verified": r["verification"]["ok"], "attempts": r["attempts"], "template_fallback_sentences": r["fallback_sentences"], "writer": r["writer"]}
    return {"false_alarms_on_clean_sentences": f"{clean_bad}/{clean_n}", "detection_rate": {k: f"{a}/{b} = {a / b:.0%}" if b else "n/a" for k, (a, b) in det.items()}, "retry_and_fallback": loop,
            "note": "Mutations are mechanical. The verifier checks numbers, sector names, direction words, causal wording and citations. It cannot judge whether a true statement is well chosen."}


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
