"""Сервис 6: еженедельный прогон агента по одному продукту.

Классический цикл tool-calling: модель → вызовы инструментов → результаты → модель,
пока модель не вернёт итоговый ответ без вызовов. Каждый шаг пишется в журнал
прогона (out/runs/<run_id>.jsonl) — это материал для аудита и регрессионных тестов.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import load_prompt
from ..llm import ChatModel
from .tools import TOOL_SCHEMAS, Toolbox


@dataclass
class RunResult:
    run_id: str
    steps: int
    decisions: list[dict[str, Any]] = field(default_factory=list)
    digest_path: str | None = None
    stopped_by_limit: bool = False


def system_prompt(product: dict[str, Any], run_date: str) -> str:
    th = product["thresholds"]
    fields = {
        "product_name": product["name"], "product_description": product["description"],
        "modules": ", ".join(product["modules"]), "run_date": run_date, **{k: str(v) for k, v in th.items()},
    }
    text = load_prompt("agent_system.md")
    for k, v in fields.items():  # не str.format: в промпте есть фигурные скобки JSON
        text = text.replace("{" + k + "}", v)
    return text


def _final_json(content: str | None) -> dict[str, Any]:
    if not content:
        return {}
    m = re.search(r"\{.*\}", content, flags=re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def run_weekly(chat: ChatModel, toolbox: Toolbox, max_steps: int = 200,
               log_dir: str | Path | None = None) -> RunResult:
    product = toolbox.product
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(product, toolbox.run_date)},
        {"role": "user", "content": f"Проведи недельный разбор обращений продукта «{product['name']}» "
                                    f"на {toolbox.run_date}."},
    ]
    log_path = Path(log_dir) / f"{toolbox.run_id}.jsonl" if log_dir else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    result = RunResult(run_id=toolbox.run_id, steps=0)
    final: dict[str, Any] = {}

    for step in range(max_steps):
        reply = chat.chat(messages, tools=TOOL_SCHEMAS)
        messages.append(reply)
        result.steps = step + 1
        calls = reply.get("tool_calls") or []
        if not calls:
            final = _final_json(reply.get("content"))
            break
        for call in calls:
            name = call["function"]["name"]
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args, out = {}, {"error": "аргументы не JSON"}
            else:
                out = toolbox.call(name, args)
            messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                             "content": json.dumps(out, ensure_ascii=False)})
            if log_path:
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"step": step, "tool": name, "args": args, "out": out},
                                       ensure_ascii=False) + "\n")
    else:
        result.stopped_by_limit = True

    for s in final.get("skipped", []):
        if isinstance(s, dict) and s.get("cluster_id"):
            toolbox.store.log_decision(toolbox.run_id, product["id"], s["cluster_id"], "SKIP", None,
                                       str(s.get("reason", ""))[:300], {}, toolbox.run_date)
    if not toolbox.digest_sent:  # страховка: дайджест уходит, даже если модель забыла его отправить
        toolbox.send_digest()
    result.digest_path = str(toolbox.sink.dir / f"{product['id']}_{toolbox.run_date}.md")
    result.decisions = toolbox.store.decisions(toolbox.run_id)
    return result


def new_run_id(product_id: str, run_date: str) -> str:
    return f"{product_id}-{run_date}-{uuid.uuid4().hex[:6]}"
