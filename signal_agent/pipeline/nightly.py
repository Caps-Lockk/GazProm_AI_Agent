"""Ночной конвейер: сервисы 1–5 подряд для одного продукта.

В бою каждый шаг — отдельный сервис с очередью между ними; здесь они вызываются
последовательно, чтобы прототип запускался одной командой.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .clustering import build_clusters
from .extraction import Extractor
from .ingestion import TicketSource, ingest
from .media import ticket_text
from .pii import mask


@dataclass
class NightlyStats:
    ingested: int
    carded: int
    needs_review: int
    clusters: int


def run_nightly(product: dict[str, Any], settings: dict[str, Any], store, source: TicketSource,
                chat, asr, vl, run_date: str) -> NightlyStats:
    ingested = ingest(source, store)
    extractor = Extractor(chat, product, retries=settings["pipeline"]["extraction_retries"])
    carded = review = 0
    for ticket in store.tickets_without_cards(product["id"]):
        masked = mask(ticket_text(ticket, asr, vl))   # ПДн убираются ДО вызова LLM
        card = extractor.extract(ticket, masked)
        store.save_card(card)
        carded += 1
        review += card.needs_review
    since = (date.fromisoformat(run_date) - timedelta(days=settings["pipeline"]["window_days"])).isoformat()
    clusters = build_clusters(store.cards(product["id"], since=since),
                              threshold=settings["pipeline"]["cluster_distance_threshold"])
    store.replace_clusters(product["id"], clusters)
    return NightlyStats(ingested, carded, review, len(clusters))
