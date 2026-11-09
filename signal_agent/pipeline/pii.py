"""Сервис 3: маскирование персональных данных до любого вызова LLM.

Правила — регулярные выражения; в бою к ним добавляется NER-модель (Natasha/DeepPavlov
во внутреннем контуре). Порядок важен: e-mail раньше логина, телефон раньше ИНН.
"""
from __future__ import annotations

import re

_UPPER_PLATE = "АВЕКМНОРСТУХ"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")),
    ("INN", re.compile(r"(?<![\d.])\d{10}(?:\d{2}|\d{3}|\d{5})?(?![\d.])")),
    ("PLATE", re.compile(rf"(?<![\w])[{_UPPER_PLATE}]\s?\d{{3}}\s?[{_UPPER_PLATE}]{{2}}\s?\d{{2,3}}(?![\w])")),
    ("FIO", re.compile(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:вич|вна|ична|чна)\b")),
    ("FIO", re.compile(r"[А-ЯЁ][а-яё]+\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.")),
    ("LOGIN", re.compile(r"(?i)(?<=логин[:\s])\s*(?!\[)[^\s\[]+")),
    ("LOGIN", re.compile(r"(?i)(?<=login[:\s])\s*(?!\[)[^\s\[]+")),
    ("PASSWORD", re.compile(r"(?i)(?<=пароль[:\s])\s*(?!\[)[^\s\[]+")),
]


def mask(text: str) -> str:
    """Заменяет найденные ПДн на метки [EMAIL], [PHONE] … Идемпотентна."""
    if not text:
        return text
    for label, pattern in PATTERNS:
        text = pattern.sub(f" [{label}]" if label in ("LOGIN", "PASSWORD") else f"[{label}]", text)
    return re.sub(r"[ \t]{2,}", " ", text)


def find_pii(text: str) -> list[str]:
    """Список найденных категорий ПДн — для проверок на выходе инструментов."""
    found = []
    for label, pattern in PATTERNS:
        if pattern.search(text or ""):
            found.append(label)
    return sorted(set(found))
