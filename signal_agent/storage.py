"""Хранилище прототипа на SQLite. В бою — PostgreSQL + pgvector с той же схемой.

Агент читает только карточки и кластеры (обезличенные); сырые тикеты лежат
отдельной таблицей, к которой у сервиса агента нет доступа (в бою — отдельная схема).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .models import Card, Cluster, Ticket

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets   (id TEXT PRIMARY KEY, product TEXT, created_at TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS cards     (ticket_id TEXT PRIMARY KEY, product TEXT, created_at TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS clusters  (id TEXT, product TEXT, data TEXT, PRIMARY KEY (id, product));
CREATE TABLE IF NOT EXISTS watermarks(name TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, product TEXT,
                                      cluster_id TEXT, decision TEXT, issue_id TEXT, reason TEXT,
                                      payload TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS feedback  (id INTEGER PRIMARY KEY AUTOINCREMENT, cluster_id TEXT, verdict TEXT,
                                      comment TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS backlog   (issue_id TEXT PRIMARY KEY, product TEXT, title TEXT, body TEXT,
                                      status TEXT, cluster_id TEXT, created_at TEXT, comments TEXT);
"""


class Store:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # --- тикеты и карточки -------------------------------------------------
    def upsert_ticket(self, t: Ticket) -> None:
        self.db.execute("INSERT OR REPLACE INTO tickets VALUES (?,?,?,?)",
                        (t.id, t.product, t.created_at, json.dumps(t.__dict__, ensure_ascii=False)))
        self.db.commit()

    def tickets_without_cards(self, product: str) -> list[Ticket]:
        rows = self.db.execute(
            "SELECT t.data FROM tickets t LEFT JOIN cards c ON c.ticket_id = t.id "
            "WHERE t.product = ? AND c.ticket_id IS NULL ORDER BY t.created_at", (product,)).fetchall()
        return [Ticket.from_dict(json.loads(r["data"])) for r in rows]

    def save_card(self, c: Card) -> None:
        self.db.execute("INSERT OR REPLACE INTO cards VALUES (?,?,?,?)",
                        (c.ticket_id, c.product, c.created_at, json.dumps(c.to_dict(), ensure_ascii=False)))
        self.db.commit()

    def cards(self, product: str, since: str | None = None) -> list[Card]:
        q, args = "SELECT data FROM cards WHERE product = ?", [product]
        if since:
            q += " AND created_at >= ?"
            args.append(since)
        return [Card(**json.loads(r["data"])) for r in self.db.execute(q + " ORDER BY created_at", args)]

    def cards_by_ids(self, ids: list[str]) -> list[Card]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = self.db.execute(f"SELECT data FROM cards WHERE ticket_id IN ({marks}) ORDER BY created_at DESC", ids)
        return [Card(**json.loads(r["data"])) for r in rows]

    # --- кластеры -----------------------------------------------------------
    def replace_clusters(self, product: str, clusters: list[Cluster]) -> None:
        self.db.execute("DELETE FROM clusters WHERE product = ?", (product,))
        self.db.executemany("INSERT INTO clusters VALUES (?,?,?)",
                            [(c.id, product, json.dumps(c.to_dict(), ensure_ascii=False)) for c in clusters])
        self.db.commit()

    def clusters(self, product: str) -> list[Cluster]:
        rows = self.db.execute("SELECT data FROM clusters WHERE product = ?", (product,))
        return [Cluster(**json.loads(r["data"])) for r in rows]

    def cluster(self, cluster_id: str) -> Cluster | None:
        r = self.db.execute("SELECT data FROM clusters WHERE id = ?", (cluster_id,)).fetchone()
        return Cluster(**json.loads(r["data"])) if r else None

    # --- служебное ------------------------------------------------------------
    def get_watermark(self, name: str) -> str | None:
        r = self.db.execute("SELECT value FROM watermarks WHERE name = ?", (name,)).fetchone()
        return r["value"] if r else None

    def set_watermark(self, name: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO watermarks VALUES (?,?)", (name, value))
        self.db.commit()

    # --- решения агента и обратная связь ------------------------------------
    def log_decision(self, run_id: str, product: str, cluster_id: str, decision: str,
                     issue_id: str | None, reason: str, payload: dict[str, Any], at: str) -> None:
        self.db.execute("INSERT INTO decisions (run_id, product, cluster_id, decision, issue_id, reason, payload, "
                        "created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (run_id, product, cluster_id, decision, issue_id, reason,
                         json.dumps(payload, ensure_ascii=False), at))
        self.db.commit()

    def decisions(self, run_id: str | None = None) -> list[dict[str, Any]]:
        q, args = "SELECT * FROM decisions", []
        if run_id:
            q, args = q + " WHERE run_id = ?", [run_id]
        return [dict(r) for r in self.db.execute(q + " ORDER BY id", args)]

    def add_feedback(self, cluster_id: str, verdict: str, comment: str, at: str) -> None:
        self.db.execute("INSERT INTO feedback (cluster_id, verdict, comment, created_at) VALUES (?,?,?,?)",
                        (cluster_id, verdict, comment, at))
        self.db.commit()

    def feedback(self, cluster_id: str) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT verdict, comment, created_at FROM feedback WHERE cluster_id = ? "
                               "ORDER BY created_at DESC", (cluster_id,))
        return [dict(r) for r in rows]
