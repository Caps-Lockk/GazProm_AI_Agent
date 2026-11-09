"""Сервис 1: инкрементальная выгрузка тикетов из системы обработки тикетов.

Агент и конвейер никогда не ходят в тикет-систему напрямую — только через этот
адаптер с read-only учёткой. Водяной знак (watermark) по updated_at хранится в БД,
поэтому повторный запуск после сбоя ничего не теряет и не дублирует.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Protocol

from ..models import Ticket


class TicketSource(Protocol):
    def fetch(self, since: str | None) -> Iterable[Ticket]: ...


class JsonlTicketSource:
    """Выгрузка из JSONL — для прототипа, тестов и бэктеста по архиву."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self, since: str | None) -> Iterable[Ticket]:
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    t = Ticket.from_dict(json.loads(line))
                    if since is None or t.created_at > since:
                        yield t


class SqlTicketSource:
    """Боевой адаптер: read-only реплика БД тикет-системы.

    Запрос параметризован по водяному знаку; схема — пример, сверяется с владельцем системы.
    """

    QUERY = """
        SELECT id, product_code AS product, channel, created_at, client_id,
               body AS text, audio_uri AS audio_ref, attachments_json
        FROM tickets
        WHERE updated_at > %(since)s AND status IN ('closed', 'resolved')
        ORDER BY updated_at
        LIMIT 5000
    """

    def __init__(self, connection_factory):
        self.connect = connection_factory

    def fetch(self, since: str | None) -> Iterable[Ticket]:  # pragma: no cover - нужен боевой контур
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute(self.QUERY, {"since": since or "1970-01-01"})
            for row in cur:
                d = dict(zip([c[0] for c in cur.description], row))
                d["attachments"] = json.loads(d.pop("attachments_json") or "[]")
                yield Ticket.from_dict(d)


def ingest(source: TicketSource, store) -> int:
    since = store.get_watermark("ingestion")
    n, newest = 0, since
    for ticket in source.fetch(since):
        store.upsert_ticket(ticket)
        n += 1
        newest = max(newest or ticket.created_at, ticket.created_at)
    if newest:
        store.set_watermark("ingestion", newest)
    return n
