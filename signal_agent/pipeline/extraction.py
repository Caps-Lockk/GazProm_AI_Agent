"""Сервис 4: обезличенный текст тикета → JSON-карточка (Qwen 3.8, температура 0).

Ответ модели проверяется по схеме. Ошибка → один повтор с текстом ошибки,
повторная ошибка → карточка с needs_review=True, тикет не теряется.
"""
from __future__ import annotations

import json
import re
from typing import Any

from ..config import load_prompt
from ..llm import ChatModel
from ..models import CARD_TYPES, CRITICALITY, Card, Ticket


def validate_card(d: Any, modules: list[str]) -> list[str]:
    errors: list[str] = []
    if not isinstance(d, dict):
        return ["ответ не JSON-объект"]
    if d.get("module") not in modules:
        errors.append(f"module должен быть одним из {modules}")
    if d.get("type") not in CARD_TYPES:
        errors.append(f"type должен быть одним из {list(CARD_TYPES)}")
    if d.get("criticality") not in CRITICALITY:
        errors.append(f"criticality должен быть одним из {list(CRITICALITY)}")
    summary = d.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 200:
        errors.append("summary — непустая строка ≤ 200 символов")
    sig = d.get("signature")
    if not isinstance(sig, str) or not (3 <= len(sig.split()) <= 12):
        errors.append("signature — 3–10 слов")
    steps = d.get("steps", [])
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        errors.append("steps — список строк")
    return errors


def _parse_json(text: str | None) -> Any:
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


class Extractor:
    def __init__(self, chat: ChatModel, product: dict[str, Any], retries: int = 1):
        self.chat = chat
        self.product = product
        self.retries = retries
        self.template = load_prompt("extract_card.md")

    def extract(self, ticket: Ticket, masked_text: str) -> Card:
        modules = self.product["modules"]
        prompt = self.template.format(
            product_name=self.product["name"], product_description=self.product["description"],
            modules=modules, channel=ticket.channel, text=masked_text,
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        data, errors = None, ["нет ответа"]
        for _ in range(self.retries + 1):
            reply = self.chat.chat(messages, json_mode=True)
            data = _parse_json(reply.get("content"))
            errors = validate_card(data, modules)
            if not errors:
                break
            messages += [reply, {"role": "user", "content":
                                 "Ответ не прошёл проверку: " + "; ".join(errors) + ". Верни исправленный JSON."}]
        base = dict(ticket_id=ticket.id, product=ticket.product, channel=ticket.channel,
                    created_at=ticket.created_at, client_id=ticket.client_id)
        if errors:
            return Card(**base, module="other", type="consultation", summary=masked_text[:200],
                        signature="Не удалось разобрать обращение", steps=[], criticality="low",
                        needs_review=True)
        return Card(**base, module=data["module"], type=data["type"], summary=data["summary"].strip(),
                    signature=data["signature"].strip(), steps=data.get("steps", []),
                    criticality=data["criticality"])
