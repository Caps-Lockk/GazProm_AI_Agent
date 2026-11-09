import json
import unittest

from signal_agent.config import load_product
from signal_agent.models import Ticket
from signal_agent.mock_llm import MockChat
from signal_agent.pipeline.extraction import Extractor, validate_card

PRODUCT = load_product("webneft")
TICKET = Ticket(id="T-1", product="webneft", channel="form", created_at="2026-11-01T10:00", client_id="c1")


class BrokenThenFixed:
    """Первый ответ — мусор, второй — валидный JSON: проверяем повтор с текстом ошибки."""
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None, json_mode=False, temperature=0.0):
        self.calls += 1
        if self.calls == 1:
            return {"role": "assistant", "content": "Конечно! Вот карточка: {type: bug"}
        return MockChat().chat(messages, json_mode=True)


class AlwaysBroken:
    def chat(self, *a, **k):
        return {"role": "assistant", "content": json.dumps({"type": "panic"})}


class TestExtraction(unittest.TestCase):
    def test_mock_card_is_valid(self):
        card = Extractor(MockChat(), PRODUCT).extract(TICKET, "Ошибка 404 при бронировании очереди")
        self.assertEqual((card.module, card.type), ("queue", "bug"))
        self.assertFalse(card.needs_review)

    def test_retry_fixes_answer(self):
        llm = BrokenThenFixed()
        card = Extractor(llm, PRODUCT, retries=1).extract(TICKET, "Не приходит СМС-код")
        self.assertEqual(llm.calls, 2)
        self.assertEqual(card.module, "auth")

    def test_fallback_needs_review(self):
        card = Extractor(AlwaysBroken(), PRODUCT, retries=1).extract(TICKET, "непонятный текст")
        self.assertTrue(card.needs_review)

    def test_validator(self):
        self.assertTrue(validate_card({"module": "x"}, PRODUCT["modules"]))
        ok = {"module": "queue", "type": "bug", "criticality": "low", "summary": "s",
              "signature": "ошибка при бронировании очереди", "steps": []}
        self.assertEqual(validate_card(ok, PRODUCT["modules"]), [])
