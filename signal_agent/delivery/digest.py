"""Сервис 7 (часть 2): еженедельный дайджест владельцу продукта.

Прототип пишет Markdown в out/digests; в бою тот же текст уходит вебхуком в
корпоративный мессенджер (канал из карточки продукта).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

LABELS = {"NEW": "Новая задача", "UPDATE": "Дополнена задача"}


def render(product: dict[str, Any], items: list[dict[str, Any]], run_date: str) -> str:
    lines = [f"# «Сигнал» · {product['name']} · неделя до {run_date}", ""]
    if not items:
        lines.append("Повторяющихся проблем выше порога за неделю не найдено.")
    for it in items:
        lines.append(f"- **{LABELS.get(it['decision'], it['decision'])} {it.get('issue_id', '')}** — "
                     f"{it['title']} ({it.get('tickets', '?')} обращ., {it.get('clients', '?')} клиент.)")
    lines += ["", "Оцените каждое предложение в трекере: «полезно», «дубль» или «не проблема» — "
                  "агент учтёт оценку в следующих прогонах."]
    return "\n".join(lines)


class FileDigestSink:
    def __init__(self, out_dir: str | Path):
        self.dir = Path(out_dir) / "digests"

    def send(self, product: dict[str, Any], text: str, run_date: str) -> str:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{product['id']}_{run_date}.md"
        path.write_text(text, encoding="utf-8")
        return str(path)
