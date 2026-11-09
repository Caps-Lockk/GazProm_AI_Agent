"""Метрики офлайн-оценки (раздел 4 решения): классификация, кластеры, решения агента, ASR."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Iterable


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    labels = sorted(set(y_true) | set(y_pred))
    f1s = []
    for lab in labels:
        tp = sum(t == lab and p == lab for t, p in zip(y_true, y_pred))
        fp = sum(t != lab and p == lab for t, p in zip(y_true, y_pred))
        fn = sum(t == lab and p != lab for t, p in zip(y_true, y_pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def purity(clusters: Iterable[list[str]], truth: dict[str, str]) -> float:
    """Доля тикетов, попавших в кластер вместе с большинством своей «настоящей» проблемы."""
    total = hit = 0
    for members in clusters:
        labels = [truth[t] for t in members if t in truth]
        if labels:
            hit += Counter(labels).most_common(1)[0][1]
            total += len(labels)
    return hit / total if total else 0.0


def cluster_to_problem(members: list[str], truth: dict[str, str]) -> str | None:
    labels = [truth[t] for t in members if t in truth]
    return Counter(labels).most_common(1)[0][0] if labels else None


def decision_scores(predicted: dict[str, str], expected: dict[str, str]) -> dict[str, float]:
    """precision/recall передачи проблем команде: NEW и UPDATE считаются «передано»."""
    sent = {p for p, d in predicted.items() if d in ("NEW", "UPDATE")}
    should = {p for p, d in expected.items() if d in ("NEW", "UPDATE")}
    tp = len(sent & should)
    exact = sum(predicted.get(p) == d for p, d in expected.items() if d != "EXCLUDED")
    n = sum(1 for d in expected.values() if d != "EXCLUDED")
    return {"precision": tp / len(sent) if sent else 0.0, "recall": tp / len(should) if should else 0.0,
            "decision_accuracy": exact / n if n else 0.0}


def wer(reference: str, hypothesis: str) -> float:
    r, h = reference.lower().split(), hypothesis.lower().split()
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r)][len(h)] / max(len(r), 1)


def group(rows: Iterable[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out
