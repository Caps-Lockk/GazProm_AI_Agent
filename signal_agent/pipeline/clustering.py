"""Сервис 5: карточки → кластеры («проблемы»). Чистая математика, без LLM.

По умолчанию — TF-IDF по символьным n-граммам сигнатуры и модуля + агломеративная
кластеризация по косинусному расстоянию. В бою векторизатор заменяется на
эмбеддинги внутренней модели (интерфейс Embedder), остальное не меняется.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Protocol

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from ..models import Card, Cluster


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray: ...


class TfidfEmbedder:
    def embed(self, texts: list[str]) -> np.ndarray:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True, sublinear_tf=True)
        return vec.fit_transform(texts).toarray()


def cluster_id(product: str, label: str) -> str:
    """Стабильный ID: та же сигнатура в следующем прогоне → тот же кластер и его фидбек."""
    return "cl-" + hashlib.sha1(f"{product}|{label.lower()}".encode()).hexdigest()[:10]


def _text(card: Card) -> str:
    return f"{card.signature} | {card.module}"


def build_clusters(cards: list[Card], threshold: float = 0.45, embedder: Embedder | None = None) -> list[Cluster]:
    if not cards:
        return []
    embedder = embedder or TfidfEmbedder()
    if len(cards) == 1:
        labels = np.array([0])
    else:
        X = embedder.embed([_text(c) for c in cards])
        model = AgglomerativeClustering(n_clusters=None, distance_threshold=threshold,
                                        metric="cosine", linkage="average")
        labels = model.fit_predict(X)
    clusters: list[Cluster] = []
    for lab in sorted(set(labels.tolist())):
        members = [c for c, l in zip(cards, labels) if l == lab]
        label = Counter(c.signature for c in members).most_common(1)[0][0]
        ctype = Counter(c.type for c in members).most_common(1)[0][0]
        module = Counter(c.module for c in members).most_common(1)[0][0]
        dates = sorted(c.created_at for c in members)
        clusters.append(Cluster(
            id=cluster_id(members[0].product, label), product=members[0].product, label=label,
            type=ctype, module=module, ticket_ids=[c.ticket_id for c in members],
            clients=len({c.client_id for c in members}), first_seen=dates[0], last_seen=dates[-1],
        ))
    return sorted(clusters, key=lambda c: -len(c.ticket_ids))
