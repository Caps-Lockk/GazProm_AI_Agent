import unittest

from signal_agent.models import Card
from signal_agent.pipeline.clustering import build_clusters, cluster_id


def card(i, sig, client="c1", module="offer"):
    return Card(ticket_id=f"T-{i}", product="webneft", channel="form", created_at=f"2026-11-0{1 + i % 8}",
                client_id=client, module=module, type="bug", summary=sig, signature=sig, steps=[],
                criticality="low")


class TestClustering(unittest.TestCase):
    def test_groups_same_problem(self):
        cards = [card(i, "Кнопка «Далее» не реагирует на шаге 2 оферты", f"c{i}") for i in range(4)]
        cards += [card(10 + i, "Ошибка 404 при бронировании электронной очереди", module="queue") for i in range(3)]
        clusters = build_clusters(cards)
        self.assertEqual(sorted(len(c.ticket_ids) for c in clusters), [3, 4])
        self.assertEqual(clusters[0].clients, 4)

    def test_stable_id(self):
        self.assertEqual(cluster_id("webneft", "Abc def ghi"), cluster_id("webneft", "abc def ghi"))
