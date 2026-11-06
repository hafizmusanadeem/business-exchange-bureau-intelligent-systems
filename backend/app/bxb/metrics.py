"""Ranking metrics (stdlib). Cross-check against ranx (github.com/AmenRa/ranx) once it is installable.
`grades` is the list of true relevance grades (0..3) in the order the system ranked the candidates."""
from math import log2

REL = 2  # grade >= 2 counts as "relevant" for precision/recall


def precision_at_k(grades: list[int], k: int) -> float:
    top = grades[:k]
    return sum(g >= REL for g in top) / k if top else 0.0


def recall_at_k(grades: list[int], k: int) -> float:
    tot = sum(g >= REL for g in grades)
    return sum(g >= REL for g in grades[:k]) / tot if tot else 0.0


def dcg(grades: list[int], k: int) -> float:
    return sum((2 ** g - 1) / log2(i + 2) for i, g in enumerate(grades[:k]))


def ndcg_at_k(grades: list[int], k: int) -> float:
    ideal = dcg(sorted(grades, reverse=True), k)
    return dcg(grades, k) / ideal if ideal > 0 else 0.0
