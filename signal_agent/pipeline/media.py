"""Сервис 2: звонки → текст (Qwen-ASR), картинки → текст ошибки (Qwen-VL).

Самая тяжёлая по GPU часть, поэтому вынесена отдельно: масштабируется своим
пулом воркеров и не блокирует обработку текстовых заявок.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from ..models import Ticket


class ASR(Protocol):
    def transcribe(self, audio_ref: str) -> str: ...


class VL(Protocol):
    def describe(self, file_ref: str) -> str: ...


class StubMedia:
    """Заглушка для прототипа: заранее подготовленные расшифровки из JSON.

    Имитирует выход Qwen-ASR/Qwen-VL, чтобы конвейер работал без GPU.
    """

    def __init__(self, path: str | Path):
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))

    def transcribe(self, audio_ref: str) -> str:
        return self.data.get(audio_ref, "")

    def describe(self, file_ref: str) -> str:
        return self.data.get(file_ref, "")


def ticket_text(ticket: Ticket, asr: ASR, vl: VL) -> str:
    """Собирает полный текст обращения: заявка + расшифровка звонка + текст со скриншотов."""
    parts = []
    if ticket.text:
        parts.append(ticket.text)
    if ticket.channel == "call" and ticket.audio_ref:
        parts.append(asr.transcribe(ticket.audio_ref))
    for att in ticket.attachments:
        if att.get("kind") == "image":
            desc = vl.describe(att["ref"])
            if desc:
                parts.append(f"[Вложение: {desc}]")
    return "\n".join(p for p in parts if p)
