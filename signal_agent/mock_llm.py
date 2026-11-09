"""Офлайн-заменитель Qwen 3.8 для демо, тестов и CI.

Это НЕ упрощение агента: оркестратор, инструменты, защиты и формат сообщений —
те же, что в бою. Заменена только модель: вместо Qwen решения принимает
детерминированная политика, которая буквально следует разделам 3–4 промпта.
Поэтому на ней удобно проверять всё, кроме качества языковой модели, — его
меряем на золотом датасете с настоящим Qwen (README, раздел «Оценка качества»).
"""
from __future__ import annotations

import json
import re
from typing import Any

# --------------------------------------------------------------------------- извлечение
RULES: list[tuple[Any, dict[str, Any]]] = [
    (lambda t: "502" in t or "сайт не открывается" in t or "недоступен у всех" in t,
     dict(module="other", type="incident", criticality="critical",
          signature="Сервис Вебнефть недоступен целиком")),
    (lambda t: "опф" in t or ("индивидуальный предприниматель" in t and "оферт" in t),
     dict(module="offer", type="bug", criticality="medium",
          signature="Неверная ОПФ: ИП вместо ООО в договоре оферты")),
    (lambda t: "далее" in t and ("не реагирует" in t or "не нажимается" in t or "ничего не происходит" in t),
     dict(module="offer", type="bug", criticality="high",
          signature="Кнопка «Далее» не реагирует на шаге 2 оферты")),
    (lambda t: "машин" in t and ("исчезла" in t or "пропала" in t or "уже внесена" in t),
     dict(module="vehicles", type="bug", criticality="medium",
          signature="Машина пропала из справочника и не добавляется повторно")),
    (lambda t: "404" in t or "время не существует" in t,
     dict(module="queue", type="bug", criticality="high",
          signature="Ошибка 404 при бронировании электронной очереди")),
    (lambda t: "телефон" in t and "заявк" in t,
     dict(module="orders", type="feature", criticality="low",
          signature="Нельзя самостоятельно изменить контактный телефон в заявке")),
    (lambda t: "уже заключ" in t,
     dict(module="account", type="access", criticality="low",
          signature="Договор уже заключён: запрос логина и пароля")),
    (lambda t: "смс" in t or "sms" in t,
     dict(module="auth", type="bug", criticality="medium",
          signature="Не приходит СМС-код для восстановления пароля")),
    (lambda t: "история заказов" in t,
     dict(module="orders", type="bug", criticality="low",
          signature="Не отображается история заказов в личном кабинете")),
    (lambda t: "закрывающ" in t or "счёт на предоплату" in t or "счет на предоплату" in t or "акт сверки" in t,
     dict(module="documents", type="consultation", criticality="low",
          signature="Запрос бухгалтерских документов по договору")),
]

STEP_HINTS = {
    "Кнопка «Далее» не реагирует на шаге 2 оферты": [
        "Открыть заключение договора оферты", "Заполнить данные организации на шаге 2",
        "Нажать «Далее» — переход не происходит"],
    "Ошибка 404 при бронировании электронной очереди": [
        "Открыть личный кабинет → «Электронная очередь»", "Выбрать дату и время налива",
        "Нажать «Забронировать» — ошибка 404 или «время не существует»"],
    "Машина пропала из справочника и не добавляется повторно": [
        "Открыть бронирование в личном кабинете", "Машины нет в списке ТС",
        "Добавить ТС заново — ошибка «машина уже внесена»"],
    "Неверная ОПФ: ИП вместо ООО в договоре оферты": [
        "Начать заключение договора оферты для ООО", "В договоре подставляется ОПФ «ИП», поле не редактируется"],
}


def mock_extract(text: str) -> dict[str, Any]:
    low = text.lower()
    for match, card in RULES:
        if match(low):
            break
    else:
        words = re.findall(r"[А-Яа-яЁё]+", text)[:6]
        card = dict(module="other", type="consultation", criticality="low",
                    signature=" ".join(words) or "Прочее обращение без категории")
        if len(card["signature"].split()) < 3:
            card["signature"] = "Прочее обращение без категории"
    first = re.split(r"(?<=[.!?])\s", text.strip())[0]
    return {**card, "summary": first[:200], "steps": STEP_HINTS.get(card["signature"], [])}


# --------------------------------------------------------------------------- агент
class _State:
    """Что модель «знает» из истории сообщений: результаты уже вызванных инструментов."""

    def __init__(self, messages: list[dict[str, Any]]):
        self.product: dict[str, Any] | None = None
        self.clusters: list[dict[str, Any]] | None = None
        self.per: dict[str, dict[str, Any]] = {}
        self.digest = False
        args_by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for m in messages:
            for c in m.get("tool_calls") or []:
                args_by_id[c["id"]] = (c["function"]["name"], json.loads(c["function"]["arguments"] or "{}"))
            if m.get("role") == "tool":
                name, args = args_by_id[m["tool_call_id"]]
                out = json.loads(m["content"])
                res = out.get("result")
                cid = args.get("cluster_id") or (m["tool_call_id"].split("__", 1)[1]
                                                 if "__" in m["tool_call_id"] else None)
                if name == "get_product_card":
                    self.product = res
                elif name == "get_clusters":
                    self.clusters = res
                elif name == "send_digest":
                    self.digest = True
                elif cid:
                    self.per.setdefault(cid, {})[name] = out


class MockChat:
    """Детерминированная «модель»: извлечение по правилам + политика агента по промпту."""

    def __init__(self):
        self._n = 0

    def _call(self, name: str, **args: Any) -> dict[str, Any]:
        self._n += 1
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": f"call_{self._n}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}]}

    def chat(self, messages, tools=None, json_mode=False, temperature=0.0):
        if not tools:
            text = messages[0]["content"].split("<<<", 1)[-1].rsplit(">>>", 1)[0]
            return {"role": "assistant", "content": json.dumps(mock_extract(text), ensure_ascii=False)}
        return self._agent_step(messages)

    # Политика = разделы 3–4 системного промпта.
    def _agent_step(self, messages):
        st = _State(messages)
        if st.product is None:
            return self._call("get_product_card")
        if st.clusters is None:
            return self._call("get_clusters", min_size=2)
        th = st.product["thresholds"]
        skipped = []
        for cl in st.clusters:
            cid, seen = cl["cluster_id"], st.per.get(cl["cluster_id"], {})
            for tool in ("get_cluster_examples", "get_cluster_trend", "get_feedback"):
                if tool not in seen:
                    return self._call(tool, cluster_id=cid)
            if any(k in seen for k in ("create_backlog_draft", "comment_existing_issue")):
                continue
            examples = seen["get_cluster_examples"]["result"]
            feedback = seen["get_feedback"]["result"]
            by_volume = cl["tickets"] >= th["min_tickets"] and cl["clients"] >= th["min_clients"]
            by_growth = cl["last_7d"] >= th["min_growth_tickets"] and cl["growth"] >= th["growth_ratio"]
            if cl["type"] in ("consultation", "access"):
                skipped.append({"cluster_id": cid, "reason": "консультация или запрос доступа без дефекта"})
                continue
            if not (by_volume or by_growth):
                skipped.append({"cluster_id": cid, "reason": "ниже порога частоты"})
                continue
            rejected = [f for f in feedback if f["verdict"] == "not_a_problem"
                        and f["days_ago"] < th["reject_cooldown_days"]]
            if rejected and cl["last_7d"] <= cl["prev_7d"]:
                skipped.append({"cluster_id": cid, "reason": f"команда отклонила {rejected[0]['days_ago']} дн. "
                                f"назад: {rejected[0]['comment']}; роста нет"})
                continue
            if "search_backlog" not in seen:
                return self._tag(self._call("search_backlog", query=cl["label"]), cid)
            matches = seen["search_backlog"].get("result") or []
            evidence = [e["ticket_id"] for e in examples]
            best = matches[0] if matches and matches[0]["score"] >= 0.35 else None
            if best and best["status"] in ("open", "in_progress"):
                return self._call("comment_existing_issue", issue_id=best["issue_id"], cluster_id=cid,
                                  comment=f"Проблема повторяется: «{cl['label']}».", evidence=evidence)
            steps = next((e["steps"] for e in examples if e["steps"]), [])
            note = f"Возможна регрессия {best['issue_id']} (задача закрыта)." if best else ""
            priority = "high" if (by_growth or cl["clients"] >= 5) else "medium"
            return self._call(
                "create_backlog_draft", cluster_id=cid, title=cl["label"][:80],
                problem=(f"{cl['tickets']} обращений от {cl['clients']} клиентов за период. "
                         f"Типичное описание: {examples[0]['summary']}"),
                steps=steps, evidence=evidence, type="feature" if cl["type"] == "feature" else
                ("ux" if cl["type"] == "ux" else "bug"), priority_hint=priority,
                confidence=0.8 if steps else 0.55, note=note)
        if not st.digest:
            return self._call("send_digest")
        return {"role": "assistant", "content": json.dumps({"skipped": skipped}, ensure_ascii=False),
                "tool_calls": None}

    @staticmethod
    def _tag(msg: dict[str, Any], cid: str) -> dict[str, Any]:
        """search_backlog не принимает cluster_id, поэтому привязку кладём в id вызова."""
        msg["tool_calls"][0]["id"] += f"__{cid}"
        return msg
