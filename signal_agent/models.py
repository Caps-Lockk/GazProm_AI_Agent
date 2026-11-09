"""Доменные объекты. Простые dataclass'ы — без ORM, чтобы прототип не тянул зависимостей."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

CARD_TYPES = ("bug", "feature", "ux", "consultation", "access", "incident")
CRITICALITY = ("low", "medium", "high", "critical")
ISSUE_TYPES = ("bug", "feature", "ux")
PRIORITIES = ("low", "medium", "high")


@dataclass
class Ticket:
    """Обращение в том виде, в каком его отдаёт система обработки тикетов."""
    id: str
    product: str
    channel: str                    # "call" | "form"
    created_at: str                 # ISO 8601
    client_id: str
    text: str = ""                  # текст заявки (для звонка пусто до транскрибации)
    audio_ref: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Ticket":
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in d.items() if k in keys})


@dataclass
class Card:
    """Обезличенная структурированная карточка — единственное, что видит агент."""
    ticket_id: str
    product: str
    channel: str
    created_at: str
    client_id: str
    module: str
    type: str
    summary: str
    signature: str
    steps: list[str]
    criticality: str
    needs_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Cluster:
    id: str
    product: str
    label: str
    type: str
    module: str
    ticket_ids: list[str]
    clients: int
    first_seen: str
    last_seen: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
