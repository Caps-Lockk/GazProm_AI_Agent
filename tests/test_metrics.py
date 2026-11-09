import unittest

from signal_agent.metrics import decision_scores, macro_f1, purity, wer


class TestMetrics(unittest.TestCase):
    def test_f1(self):
        self.assertEqual(macro_f1(["a", "b"], ["a", "b"]), 1.0)
        self.assertLess(macro_f1(["a", "b"], ["a", "a"]), 1.0)

    def test_purity(self):
        self.assertEqual(purity([["1", "2"], ["3"]], {"1": "x", "2": "y", "3": "y"}), 2 / 3)

    def test_wer(self):
        self.assertEqual(wer("не приходит смс код", "не приходит смс код"), 0)
        self.assertEqual(wer("не приходит смс код", "не приходит код"), 0.25)

    def test_decisions(self):
        s = decision_scores({"a": "NEW", "b": "NEW"}, {"a": "NEW", "b": "SKIP"})
        self.assertEqual((s["precision"], s["recall"]), (0.5, 1.0))
