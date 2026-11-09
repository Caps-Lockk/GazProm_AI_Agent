"""Защиты инструментов — то, что не должно зависеть от качества модели."""
import unittest

from signal_agent.agent.tools import Toolbox
from signal_agent.config import load_product, load_settings
from signal_agent.delivery.digest import FileDigestSink
from signal_agent.delivery.tracker import SqliteTracker
from signal_agent.models import Card
from signal_agent.pipeline.clustering import build_clusters
from signal_agent.storage import Store
import tempfile


def make(n_tickets=6, n_clients=4, sig="Кнопка «Далее» не реагирует на шаге 2 оферты", max_writes=15):
    settings = load_settings()
    settings["agent"]["max_writes_per_run"] = max_writes
    product = load_product("webneft")
    store = Store()
    cards = [Card(ticket_id=f"T-{i}", product="webneft", channel="form", created_at="2026-11-05T10:00",
                  client_id=f"c{i % n_clients}", module="offer", type="bug", summary="s", signature=sig,
                  steps=["шаг"], criticality="medium") for i in range(n_tickets)]
    for c in cards:
        store.save_card(c)
    clusters = build_clusters(cards)
    store.replace_clusters("webneft", clusters)
    tb = Toolbox(store, SqliteTracker(store), FileDigestSink(tempfile.mkdtemp()), product, settings,
                 "2026-11-08", "run-1")
    return tb, clusters[0]


ARGS = dict(title="Кнопка «Далее» не реагирует", problem="Описание", type="bug",
            priority_hint="high", confidence=0.8, steps=["шаг"])


class TestToolGuards(unittest.TestCase):
    def test_creates_and_is_idempotent(self):
        tb, cl = make()
        r1 = tb.call("create_backlog_draft", dict(cluster_id=cl.id, evidence=["T-0", "T-1"], **ARGS))
        r2 = tb.call("create_backlog_draft", dict(cluster_id=cl.id, evidence=["T-0"], **ARGS))
        self.assertEqual(r1["result"]["status"], "created")
        self.assertEqual(r2["result"]["status"], "already_exists")

    def test_rejects_foreign_evidence(self):
        tb, cl = make()
        r = tb.call("create_backlog_draft", dict(cluster_id=cl.id, evidence=["T-999"], **ARGS))
        self.assertIn("не из этого кластера", r["error"])

    def test_rejects_pii(self):
        tb, cl = make()
        args = {**ARGS, "problem": "Клиент Иванов Пётр Сергеевич, +7 912 345 67 89"}
        r = tb.call("create_backlog_draft", dict(cluster_id=cl.id, evidence=["T-0"], **args))
        self.assertIn("персональные данные", r["error"])

    def test_rejects_below_threshold(self):
        tb, cl = make(n_tickets=2, n_clients=2)
        r = tb.call("create_backlog_draft", dict(cluster_id=cl.id, evidence=["T-0"], **ARGS))
        self.assertIn("ниже порога", r["error"])

    def test_write_limit(self):
        tb, cl = make(max_writes=0)
        r = tb.call("create_backlog_draft", dict(cluster_id=cl.id, evidence=["T-0"], **ARGS))
        self.assertIn("лимит", r["error"])

    def test_closed_issue_cannot_be_commented(self):
        tb, cl = make()
        tb.tracker.seed([{"issue_id": "WN-1", "product": "webneft", "title": "x", "status": "closed",
                          "created_at": "2026-01-01"}])
        r = tb.call("comment_existing_issue", dict(issue_id="WN-1", cluster_id=cl.id, comment="c", evidence=["T-0"]))
        self.assertIn("закрыта", r["error"])

    def test_unknown_tool_and_bad_args(self):
        tb, _ = make()
        self.assertIn("error", tb.call("drop_database", {}))
        self.assertIn("неверные аргументы", tb.call("get_clusters", {"foo": 1})["error"])

    def test_digest_once(self):
        tb, _ = make()
        self.assertIn("result", tb.call("send_digest", {}))
        self.assertIn("уже отправлен", tb.call("send_digest", {})["error"])
