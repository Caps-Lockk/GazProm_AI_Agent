"""Цифры отчёта должны воспроизводиться моделью."""
import unittest

from finance.model import SCENARIOS, present_value, yearly_effect


class TestFinance(unittest.TestCase):
    def test_report_numbers(self):
        expected = {"Пессимистичный": (7.8, 5.6), "Базовый": (15.6, 11.1), "Оптимистичный": (25.5, 18.2)}
        for s in SCENARIOS:
            flows = [y["total"] for y in yearly_effect(s)]
            self.assertAlmostEqual(sum(flows) / 1e6, expected[s.name][0], places=1)
            self.assertAlmostEqual(present_value(flows, 0.17) / 1e6, expected[s.name][1], places=1)
