"""Инструменты агента (9 штук: 6 на чтение, 3 на запись).

Защиты живут здесь, а не в промпте: даже если модель ошибётся или поддастся
инструкции из текста тикета, инструмент не создаст задачу ниже порога, с чужими
доказательствами, с персональными данными или сверх лимита записей.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Callable

from ..models import ISSUE_TYPES, PRIORITIES, Cluster
from ..pipeline.pii import find_pii
from ..delivery import digest as digest_mod


def _d(iso: str) -> date:
    return date.fromisoformat(iso[:10])


class ToolError(Exception):
    pass


class Toolbox:
    def __init__(self, store, tracker, digest_sink, product: dict[str, Any], settings: dict[str, Any],
                 run_date: str, run_id: str):
        self.store, self.tracker, self.sink = store, tracker, digest_sink
        self.product, self.settings = product, settings
        self.th = product["thresholds"]
        self.run_date, self.run_id = run_date, run_id
        self.writes = 0
        self.digest_sent = False
        self.max_writes = settings["agent"]["max_writes_per_run"]

    # ------------------------------------------------------------------ helpers
    def _cluster(self, cluster_id: str) -> Cluster:
        c = self.store.cluster(cluster_id)
        if not c or c.product != self.product["id"]:
            raise ToolError(f"кластер {cluster_id} не найден у продукта {self.product['id']}")
        return c

    def _stats(self, c: Cluster) -> dict[str, Any]:
        run = _d(self.run_date)
        cards = self.store.cards_by_ids(c.ticket_ids)
        start = run - timedelta(days=self.th["period_days"])
        in_period = [x for x in cards if _d(x.created_at) > start]
        last7 = sum(1 for x in cards if run - timedelta(days=7) < _d(x.created_at) <= run)
        prev7 = sum(1 for x in cards if run - timedelta(days=14) < _d(x.created_at) <= run - timedelta(days=7))
        return {"tickets": len(in_period), "clients": len({x.client_id for x in in_period}),
                "last_7d": last7, "prev_7d": prev7,
                "growth": round(last7 / prev7, 2) if prev7 else (float(last7) if last7 else 0.0),
                "critical": any(x.criticality == "critical" for x in cards)}

    def _eligible(self, s: dict[str, Any]) -> bool:
        by_volume = s["tickets"] >= self.th["min_tickets"] and s["clients"] >= self.th["min_clients"]
        by_growth = s["last_7d"] >= self.th["min_growth_tickets"] and s["growth"] >= self.th["growth_ratio"]
        return by_volume or by_growth

    def _check_text(self, *parts: Any) -> None:
        text = json.dumps(parts, ensure_ascii=False)
        pii = find_pii(text)
        if pii:
            raise ToolError(f"текст содержит персональные данные ({', '.join(pii)}) — убери их")

    def _check_evidence(self, c: Cluster, evidence: list[str]) -> None:
        if not evidence:
            raise ToolError("evidence пуст: укажи ID тикетов из get_cluster_examples")
        foreign = sorted(set(evidence) - set(c.ticket_ids))
        if foreign:
            raise ToolError(f"ID не из этого кластера: {foreign}")

    def _write_slot(self) -> None:
        if self.writes >= self.max_writes:
            raise ToolError(f"лимит записей за прогон ({self.max_writes}) исчерпан")
        self.writes += 1

    # ------------------------------------------------------------------ read tools
    def get_product_card(self) -> dict[str, Any]:
        p = self.product
        return {"id": p["id"], "name": p["name"], "description": p["description"],
                "modules": p["modules"], "owner": p["owner"], "thresholds": p["thresholds"]}

    def get_clusters(self, min_size: int = 2) -> list[dict[str, Any]]:
        out = []
        for c in self.store.clusters(self.product["id"]):
            s = self._stats(c)
            if c.type == "incident" or s["critical"] or s["tickets"] < min_size:
                continue  # инциденты — процесс дежурной смены, не агента
            out.append({"cluster_id": c.id, "label": c.label, "type": c.type, "module": c.module, **{
                k: v for k, v in s.items() if k != "critical"}})
        return sorted(out, key=lambda x: (-x["tickets"], x["cluster_id"]))

    def get_cluster_examples(self, cluster_id: str, n: int | None = None) -> list[dict[str, Any]]:
        c = self._cluster(cluster_id)
        n = min(n or self.settings["agent"]["examples_per_cluster"], 10)
        cards = self.store.cards_by_ids(c.ticket_ids)[:n]
        return [{"ticket_id": x.ticket_id, "date": x.created_at[:10], "channel": x.channel,
                 "summary": x.summary, "steps": x.steps, "needs_review": x.needs_review} for x in cards]

    def get_cluster_trend(self, cluster_id: str, weeks: int = 4) -> list[dict[str, Any]]:
        c = self._cluster(cluster_id)
        run = _d(self.run_date)
        cards = self.store.cards_by_ids(c.ticket_ids)
        out = []
        for w in range(weeks - 1, -1, -1):
            hi = run - timedelta(days=7 * w)
            lo = hi - timedelta(days=7)
            out.append({"week_ending": hi.isoformat(),
                        "tickets": sum(1 for x in cards if lo < _d(x.created_at) <= hi)})
        return out

    def search_backlog(self, query: str) -> list[dict[str, Any]]:
        return self.tracker.search(self.product["id"], query)

    def get_feedback(self, cluster_id: str) -> list[dict[str, Any]]:
        self._cluster(cluster_id)
        run = _d(self.run_date)
        return [{**f, "days_ago": (run - _d(f["created_at"])).days} for f in self.store.feedback(cluster_id)]

    # ------------------------------------------------------------------ write tools
    def create_backlog_draft(self, cluster_id: str, title: str, problem: str, evidence: list[str],
                             type: str, priority_hint: str, confidence: float, steps: list[str] | None = None,
                             needs_review: bool = False, note: str = "") -> dict[str, Any]:
        c = self._cluster(cluster_id)
        existing = self.tracker.find_by_cluster(cluster_id)
        if existing:
            return {"issue_id": existing, "status": "already_exists"}
        s = self._stats(c)
        if not self._eligible(s):
            raise ToolError(f"кластер ниже порога: {s['tickets']} обращ., {s['clients']} клиент., "
                            f"рост {s['growth']}")
        if not title or len(title) > 80:
            raise ToolError("title обязателен и не длиннее 80 символов")
        if type not in ISSUE_TYPES or priority_hint not in PRIORITIES:
            raise ToolError(f"type ∈ {ISSUE_TYPES}, priority_hint ∈ {PRIORITIES}")
        if not 0 <= float(confidence) <= 1:
            raise ToolError("confidence должен быть от 0 до 1")
        steps = steps or []
        self._check_evidence(c, evidence)
        self._check_text(title, problem, steps, note)
        self._write_slot()
        needs_review = needs_review or not steps or float(confidence) < 0.6
        body = "\n".join([
            problem, "",
            "Шаги воспроизведения:" if steps else "Шаги воспроизведения: нет в обращениях, нужна проверка.",
            *[f"{i}. {st}" for i, st in enumerate(steps, 1)], "",
            f"Влияние: {s['tickets']} обращений от {s['clients']} клиентов за {self.th['period_days']} дн.; "
            f"за последнюю неделю {s['last_7d']}, за предыдущую {s['prev_7d']}.",
            f"Доказательства: {', '.join(evidence)}",
            *( [note] if note else [] ),
            f"Создано агентом «Сигнал», уверенность {float(confidence):.2f}"
            + (", требуется проверка человеком." if needs_review else "."),
        ])
        issue_id = self.tracker.create_draft(self.product["id"], cluster_id, title, body, self.run_date)
        self.store.log_decision(self.run_id, self.product["id"], cluster_id, "NEW", issue_id, problem,
                                {"title": title, "type": type, "priority_hint": priority_hint,
                                 "confidence": confidence, "evidence": evidence, "needs_review": needs_review,
                                 **s}, self.run_date)
        return {"issue_id": issue_id, "status": "created", "needs_review": needs_review}

    def comment_existing_issue(self, issue_id: str, cluster_id: str, comment: str,
                               evidence: list[str]) -> dict[str, Any]:
        c = self._cluster(cluster_id)
        issue = self.tracker.get(issue_id)
        if not issue or issue["product"] != self.product["id"]:
            raise ToolError(f"задача {issue_id} не найдена")
        if issue["status"] in ("closed", "done", "rejected"):
            raise ToolError(f"задача {issue_id} закрыта — для регрессии создай новую (NEW)")
        self._check_evidence(c, evidence)
        self._check_text(comment)
        self._write_slot()
        s = self._stats(c)
        text = (f"{comment}\nНовые обращения: {s['tickets']} за {self.th['period_days']} дн. от "
                f"{s['clients']} клиентов. Доказательства: {', '.join(evidence)}. — агент «Сигнал»")
        self.tracker.comment(issue_id, text, self.run_date)
        self.store.log_decision(self.run_id, self.product["id"], cluster_id, "UPDATE", issue_id, comment,
                                {"title": issue["title"], "evidence": evidence, **s}, self.run_date)
        return {"issue_id": issue_id, "status": "commented"}

    def send_digest(self, cluster_ids: list[str] | None = None) -> dict[str, Any]:
        if self.digest_sent:
            raise ToolError("дайджест за этот прогон уже отправлен")
        logged = [d for d in self.store.decisions(self.run_id) if d["decision"] in ("NEW", "UPDATE")]
        if cluster_ids:
            unknown = set(cluster_ids) - {d["cluster_id"] for d in logged}
            if unknown:
                raise ToolError(f"по кластерам {sorted(unknown)} в этом прогоне нет решений NEW/UPDATE")
        items = []
        for d in logged:
            p = json.loads(d["payload"])
            items.append({"decision": d["decision"], "issue_id": d["issue_id"], "title": p["title"],
                          "tickets": p.get("tickets"), "clients": p.get("clients")})
        text = digest_mod.render(self.product, items, self.run_date)
        path = self.sink.send(self.product, text, self.run_date)
        self.digest_sent = True
        return {"status": "sent", "items": len(items), "path": path}

    # ------------------------------------------------------------------ dispatch
    def registry(self) -> dict[str, Callable[..., Any]]:
        return {name: getattr(self, name) for name in TOOL_NAMES}

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = self.registry().get(name)
        if fn is None:
            return {"error": f"неизвестный инструмент {name}"}
        try:
            return {"result": fn(**args)}
        except ToolError as exc:
            return {"error": str(exc)}
        except TypeError as exc:
            return {"error": f"неверные аргументы: {exc}"}


TOOL_NAMES = ["get_product_card", "get_clusters", "get_cluster_examples", "get_cluster_trend",
              "search_backlog", "get_feedback", "create_backlog_draft", "comment_existing_issue", "send_digest"]


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": required, "additionalProperties": False}}}


_S = {"type": "string"}
_IDS = {"type": "array", "items": _S}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn("get_product_card", "Карточка продукта: модули, владелец, пороги решений.", {}, []),
    _fn("get_clusters", "Кластеры обращений за период разбора: размер, клиенты, тренд, тип. "
        "Инциденты уже исключены.", {"min_size": {"type": "integer", "minimum": 1}}, []),
    _fn("get_cluster_examples", "Обезличенные карточки обращений кластера с ID тикетов.",
        {"cluster_id": _S, "n": {"type": "integer", "minimum": 1, "maximum": 10}}, ["cluster_id"]),
    _fn("get_cluster_trend", "Число обращений кластера по неделям.",
        {"cluster_id": _S, "weeks": {"type": "integer", "minimum": 2, "maximum": 12}}, ["cluster_id"]),
    _fn("search_backlog", "Поиск похожих задач в трекере продукта (со статусами).", {"query": _S}, ["query"]),
    _fn("get_feedback", "Прошлые оценки продуктовой команды по кластеру.", {"cluster_id": _S}, ["cluster_id"]),
    _fn("create_backlog_draft", "Создать черновик задачи по кластеру (решение NEW).", {
        "cluster_id": _S, "title": {"type": "string", "maxLength": 80}, "problem": _S,
        "steps": _IDS, "evidence": _IDS, "type": {"type": "string", "enum": list(ISSUE_TYPES)},
        "priority_hint": {"type": "string", "enum": list(PRIORITIES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1}, "needs_review": {"type": "boolean"},
        "note": _S}, ["cluster_id", "title", "problem", "evidence", "type", "priority_hint", "confidence"]),
    _fn("comment_existing_issue", "Добавить новые случаи к открытой задаче (решение UPDATE).",
        {"issue_id": _S, "cluster_id": _S, "comment": _S, "evidence": _IDS},
        ["issue_id", "cluster_id", "comment", "evidence"]),
    _fn("send_digest", "Отправить недельный дайджест владельцу продукта (один раз за прогон).",
        {"cluster_ids": _IDS}, []),
]
