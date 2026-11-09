import unittest

from signal_agent.pipeline.pii import find_pii, mask


class TestPII(unittest.TestCase):
    def test_masks_all_categories(self):
        t = ("Иванов Пётр Сергеевич, тел. +7 (912) 345-67-89, 8 912 345 67 89, ivanov@zniva.ru, "
             "ИНН 7701234567, машина А123ВС77, логин: zniva_admin, Петрова А.С.")
        m = mask(t)
        for raw in ("Иванов", "345-67-89", "ivanov@", "7701234567", "А123ВС77", "zniva_admin", "Петрова"):
            self.assertNotIn(raw, m)
        self.assertEqual(find_pii(m), [])

    def test_keeps_business_data(self):
        t = "Отгрузка 11.07.2026, заявка № 4512, 10 тонн, ООО «Золотая Нива»"
        self.assertEqual(mask(t), t)

    def test_idempotent(self):
        t = "Звоните +7 912 345 67 89"
        self.assertEqual(mask(mask(t)), mask(t))
