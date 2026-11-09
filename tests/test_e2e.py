"""Сквозной прогон: конвейер + агент + оценка на синтетических обращениях «Вебнефти»."""
import json
import unittest

from signal_agent.app import evaluate, run_demo
from signal_agent.config import load_settings
from signal_agent.pipeline.pii import find_pii


class TestEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = load_settings()
        settings["out_dir"] = "out/test"
        cls.store, cls.nightly, cls.result = run_demo(settings)

    def test_all_tickets_carded(self):
        self.assertEqual(self.nightly.ingested, self.nightly.carded)

    def test_decisions_match_expected(self):
        report = evaluate(self.store, self.result)
        for pid, row in report["per_problem"].items():
            self.assertEqual(row["expected"], row["predicted"], pid)

    def test_no_pii_leaves_the_system(self):
        rows = self.store.db.execute("SELECT title, body, comments FROM backlog").fetchall()
        for r in rows:
            self.assertEqual(find_pii(" ".join(r)), [], r[0])
        for card in self.store.cards("webneft"):
            self.assertEqual(find_pii(json.dumps(card.to_dict(), ensure_ascii=False)), [], card.ticket_id)

    def test_incident_never_reaches_agent(self):
        payloads = " ".join(d["payload"] for d in self.result.decisions)
        self.assertNotIn("недоступен", payloads)

    def test_regression_flag_on_closed_issue(self):
        body = self.store.db.execute("SELECT body FROM backlog WHERE title LIKE '%404%' AND status='draft'"
                                     ).fetchone()[0]
        self.assertIn("регрессия WN-377", body)

    def test_finished_without_step_limit(self):
        self.assertFalse(self.result.stopped_by_limit)
