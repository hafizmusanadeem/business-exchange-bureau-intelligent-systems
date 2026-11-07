"""Module 8a: listing screening. Rules first, a statistical outlier model second, humans decide.

WHY: every listing is moderated by hand today (admin approval, "License Verified" badge). Most listings are fine, so
a cheap screen that only flags the odd ones lets staff look at 5% of listings instead of 100%.

DESIGN
  * Rules are explainable and each one carries a plain-English message for the moderator.
  * Severity: high = 40 points, medium = 25, low = 10 (capped at 100).
      score >= 60 -> "hold"    (do not publish until a person has looked)
      score >= 25 -> "review"  (a person should look)
      otherwise   -> "clear"
  * The IsolationForest signal is "low" on purpose: it can add weight to other flags but never holds a listing alone.
  * Thresholds are illustrative heuristics. Tune them on BXB's real moderation decisions before relying on them.
  * Nothing here proves fraud. A flag is a prompt for a human check.

Pure Python (numpy / scikit-learn only for the optional outlier model)."""
from __future__ import annotations

import math
import random
import re
from collections import Counter
from statistics import median

WEIGHT = {"high": 40, "medium": 25, "low": 10}
REVIEW_AT, HOLD_AT = 25, 60
_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}

_RETURN_PROMISE = re.compile(
    r"\b(guaranteed|fixed|assured)[\s-]*(returns?|roi|profit)\b"
    r"|\broi\b[^.|\n]{0,20}\d+\s?%|\bsecurity cheque\b|\brisk[\s-]*free\b|\bdouble your\b",
    re.I,
)
_CONTACT = re.compile(
    r"[\w.+-]+@[\w-]+\.\w+|https?://|www\.|\bwhats\s?app\b|\btelegram\b|\+?\d[\d\s().-]{8,}\d", re.I
)


def _flag(code: str, severity: str, message: str) -> dict:
    return {"code": code, "severity": severity, "message": message}


def sector_stats(listings: list[dict]) -> dict[str, tuple[float, float, int]]:
    """{sector: (median log10 revenue, MAD of log10 revenue, n)} used by the peer-outlier rule."""
    by: dict[str, list[float]] = {}
    for l in listings:
        if l["annual_revenue"] > 0:
            by.setdefault(l["sector"], []).append(math.log10(l["annual_revenue"]))
    out = {}
    for s, xs in by.items():
        med = median(xs)
        out[s] = (med, median(abs(x - med) for x in xs), len(xs))
    return out


def screen_listing(
    l: dict,
    *,
    text: str = "",
    employees: int | None = None,
    image_sha256: str | None = None,
    stats: dict | None = None,
    known_image_hashes: set[str] | frozenset[str] = frozenset(),
    statistical_outlier: bool = False,
) -> dict:
    """l needs: sector, annual_revenue, ebitda, asking_price. Returns {score, status, flags}."""
    flags: list[dict] = []
    rev, eb, ask = l["annual_revenue"], l["ebitda"], l["asking_price"]

    if rev > 0 and eb >= rev:
        flags.append(_flag("EBITDA_EXCEEDS_REVENUE", "high",
                           f"EBITDA (AED {eb:,}) is not below revenue (AED {rev:,}); profit cannot exceed sales."))
    elif rev > 0 and eb / rev > 0.6:
        flags.append(_flag("MARGIN_OUTLIER", "medium", f"EBITDA margin of {eb / rev:.0%} is unusually high for an SME. Ask for evidence."))
    if eb <= 0:
        flags.append(_flag("NON_POSITIVE_EBITDA", "medium", "EBITDA is zero or negative; confirm the earnings figure and what the asking price is based on."))
    else:
        m = ask / eb
        if m < 0.5:
            flags.append(_flag("PRICE_FAR_BELOW_EARNINGS", "high",
                               f"Asking price is only {m:.2f}x EBITDA, which implies payback in months. Check units, ownership share and whether this is a sale at all."))
        elif m > 25:
            flags.append(_flag("PRICE_FAR_ABOVE_EARNINGS", "medium", f"Asking price is {m:.0f}x EBITDA, far above normal SME multiples."))
    if rev > 0:
        pr = ask / rev
        if pr < 0.05:
            flags.append(_flag("PRICE_FAR_BELOW_REVENUE", "medium", f"Asking price is {pr:.3f}x annual revenue; check units and ownership share."))
        elif pr > 5:
            flags.append(_flag("PRICE_FAR_ABOVE_REVENUE", "medium", f"Asking price is {pr:.1f}x annual revenue."))
    if employees and employees >= 50 and ask / employees < 5_000:
        flags.append(_flag("PRICE_TINY_FOR_HEADCOUNT", "medium",
                           f"Asking price of AED {ask:,} for {employees:,} employees is under AED 5,000 per head; the figures do not describe the same business."))

    if stats and l["sector"] in stats and rev > 0:
        med, mad, n = stats[l["sector"]]
        if n >= 8 and mad > 0:
            z = (math.log10(rev) - med) / (1.4826 * mad)
            if abs(z) > 5:
                flags.append(_flag("REVENUE_OUTLIER_FOR_SECTOR", "medium",
                                   f"Revenue is an extreme outlier among {l['sector']} listings (robust z = {z:.1f})."))

    if text:
        if _RETURN_PROMISE.search(text):
            flags.append(_flag("RETURN_PROMISE_LANGUAGE", "high",
                               "Text promises returns or a security cheque. That reads like an investment product, not the sale of a business."))
        if _CONTACT.search(text):
            flags.append(_flag("CONTACT_DETAILS_IN_TEXT", "medium",
                               "Text contains contact details, which lets buyers and sellers bypass the platform. Remove before publishing."))
        if text.count("|") >= 3:
            flags.append(_flag("KEYWORD_STUFFING", "low", "Title or text is stuffed with separator-delimited keywords; normalise it."))
        letters = [c for c in text if c.isalpha()]
        if len(letters) >= 20 and sum(c.isupper() for c in letters) / len(letters) > 0.6:
            flags.append(_flag("SHOUTING", "low", "Text is mostly capital letters."))

    if image_sha256 and image_sha256 in known_image_hashes:
        flags.append(_flag("DUPLICATE_IMAGE", "medium", "The same image is used by another listing. Ask for proof the photo shows this business."))
    if statistical_outlier:
        flags.append(_flag("STATISTICAL_OUTLIER", "low", "The combination of revenue, margin, price and age is unusual compared with other listings."))

    flags.sort(key=lambda f: _SEV_ORDER[f["severity"]])
    score = min(100, sum(WEIGHT[f["severity"]] for f in flags))
    status = "hold" if score >= HOLD_AT else "review" if score >= REVIEW_AT else "clear"
    return {"score": score, "status": status, "flags": flags}


def outlier_ids(listings: list[dict], contamination: float = 0.02, min_n: int = 50, seed: int = 0) -> set:
    """Ids of listings an IsolationForest finds unusual. Empty if scikit-learn is missing or the set is small."""
    if len(listings) < min_n:
        return set()
    try:
        import numpy as np
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return set()
    X = np.array([[math.log10(max(l["annual_revenue"], 1)),
                   max(-1.0, min(2.0, l["ebitda"] / max(l["annual_revenue"], 1))),
                   math.log10(max(l["asking_price"], 1)),
                   math.log10(max(l["asking_price"], 1) / max(l["ebitda"], 1)),
                   float(l.get("years_operating", 0))] for l in listings])
    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=seed).fit(X)
    return {l["id"] for l, p in zip(listings, model.predict(X)) if p == -1}


def screen_all(listings: list[dict], extras: dict[int, dict] | None = None) -> dict[int, dict]:
    """Screen a batch. extras maps listing id -> {text, employees, image_sha256} for fields the table does not store."""
    extras = extras or {}
    stats = sector_stats(listings)
    hashes = Counter(e["image_sha256"] for e in extras.values() if e.get("image_sha256"))
    dup = {h for h, c in hashes.items() if c >= 2}
    odd = outlier_ids(listings)
    return {
        l["id"]: screen_listing(
            l,
            text=extras.get(l["id"], {}).get("text", ""),
            employees=extras.get(l["id"], {}).get("employees"),
            image_sha256=extras.get(l["id"], {}).get("image_sha256"),
            stats=stats,
            known_image_hashes=dup,
            statistical_outlier=l["id"] in odd,
        )
        for l in listings
    }


# Invented examples for the demo screen. None of these is a real listing.
DEMO_CASES = [
    {"title": "Invented: investment product dressed as a business sale",
     "listing": dict(id=-1, sector="Commercial Services", annual_revenue=180_000_000, ebitda=30_000_000, asking_price=400_000),
     "text": "Fleet returns opportunity | Guaranteed 20% fixed returns | Security cheque provided | Asset backed. WhatsApp +971 50 000 0000",
     "employees": 3500},
    {"title": "Invented: profit larger than sales",
     "listing": dict(id=-2, sector="Retail", annual_revenue=2_000_000, ebitda=2_600_000, asking_price=6_000_000), "text": "Neighbourhood grocery, two branches."},
    {"title": "Invented: price far below earnings",
     "listing": dict(id=-3, sector="Beauty", annual_revenue=2_500_000, ebitda=600_000, asking_price=150_000), "text": "Salon, motivated seller."},
    {"title": "Invented: contact details in the description",
     "listing": dict(id=-4, sector="Food & Beverage", annual_revenue=3_000_000, ebitda=600_000, asking_price=2_100_000),
     "text": "Busy cafe. Call 0501234567 or email owner@example.com to skip the platform."},
    {"title": "Invented: same photo as another listing",
     "listing": dict(id=-5, sector="Logistics", annual_revenue=4_000_000, ebitda=800_000, asking_price=3_200_000),
     "text": "Last-mile courier fleet.", "image_sha256": "demo-image-hash-1", "duplicate_of": True},
    {"title": "Invented: ordinary listing (should be clear)",
     "listing": dict(id=-6, sector="Healthcare", annual_revenue=5_000_000, ebitda=1_000_000, asking_price=4_500_000),
     "text": "Established dental clinic with two chairs and a long lease."},
]


def run_demo() -> list[dict]:
    known = {c["image_sha256"] for c in DEMO_CASES if c.get("duplicate_of")}
    out = []
    for c in DEMO_CASES:
        r = screen_listing(c["listing"], text=c.get("text", ""), employees=c.get("employees"),
                           image_sha256=c.get("image_sha256"), known_image_hashes=known)
        out.append({"title": c["title"], "text": c.get("text", ""), "employees": c.get("employees"),
                    "listing": {k: v for k, v in c["listing"].items() if k != "id"}, **r})
    return out


def evaluate(seed: int = 3, n_planted: int = 60) -> dict:
    """Detection of planted problems and false alarms on clean SYNTHETIC listings. Not BXB performance."""
    try:
        from app.bxb.synthetic import generate
    except ImportError:
        from synthetic import generate
    L = generate(seed=seed, n_investors=5)["listings"]
    rng = random.Random(seed)
    stats = sector_stats(L)
    base = screen_all(L)
    false_alarms = sum(r["status"] != "clear" for r in base.values())

    def ebitda_over(l): return dict(l, ebitda=round(l["annual_revenue"] * 1.4)), {}
    def cheap(l): return dict(l, asking_price=max(1, round(l["ebitda"] * 0.2))), {}
    def promise(l): return l, {"text": "Guaranteed 18% fixed returns with security cheque"}
    def contact(l): return l, {"text": "Call +971 50 123 4567 or email owner@example.com"}
    def headcount(l): return l, {"employees": max(50, int(l["asking_price"] / 1000))}
    def dupimg(l): return l, {"image_sha256": "planted"}

    plants = {"ebitda_exceeds_revenue": ebitda_over, "price_far_below_earnings": cheap, "return_promise_text": promise,
              "contact_leak_text": contact, "tiny_price_for_headcount": headcount, "duplicate_image": dupimg}
    det = {}
    for name, fn in plants.items():
        hit = 0
        for l in rng.sample(L, n_planted):
            l2, extra = fn(l)
            r = screen_listing(l2, stats=stats, known_image_hashes={"planted"}, **extra)
            hit += r["status"] != "clear"
        det[name] = f"{hit}/{n_planted} = {hit / n_planted:.0%}"
    return {"listings_screened": len(L), "false_alarms_on_clean_synthetic": f"{false_alarms}/{len(L)}",
            "detection_rate": det, "note": "Planted problems are mechanical. Tune thresholds on real moderation decisions."}


if __name__ == "__main__":
    import json
    print(json.dumps(evaluate(), indent=2))
