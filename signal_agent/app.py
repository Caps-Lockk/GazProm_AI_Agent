"""Сборка компонентов и сценарии запуска: ночной конвейер, недельный агент, офлайн-оценка."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .agent.orchestrator import RunResult, new_run_id, run_weekly
from .agent.tools import Toolbox
from .config import ROOT, load_product, load_prompt
from .delivery.digest import FileDigestSink
from .delivery.tracker import SqliteTracker
from .llm import OpenAICompatChat, QwenASR, QwenVL
from .metrics import cluster_to_problem, decision_scores, macro_f1, purity
from .mock_llm import MockChat
from .pipeline.clustering import cluster_id
from .pipeline.ingestion import JsonlTicketSource
from .pipeline.media import StubMedia
from .pipeline.nightly import NightlyStats, run_nightly
from .storage import Store

DATA = ROOT / "data"


def make_models(settings: dict[str, Any], offline: bool):
    """offline=True — офлайн-модель и заглушки медиа; иначе внутренние Qwen-модели."""
    if offline:
        stub = StubMedia(DATA / "media_stub.json")
        return MockChat(), stub, stub
    chat = OpenAICompatChat(settings["llm"]["base_url"], settings["llm"]["model"], settings["llm"]["timeout_s"])
    asr = QwenASR(settings["asr"]["base_url"], settings["asr"]["model"])
    vl = QwenVL(settings["vl"]["base_url"], settings["vl"]["model"], load_prompt("media.md"))
    return chat, asr, vl


def seed_demo(store: Store, tracker: SqliteTracker, product_id: str) -> None:
    """Исходное состояние трекера и прошлые оценки команды — как будто агент уже работал."""
    tracker.seed(json.loads((DATA / "backlog_seed.json").read_text(encoding="utf-8")))
    for f in json.loads((DATA / "feedback_seed.json").read_text(encoding="utf-8")):
        store.add_feedback(cluster_id(product_id, f["label"]), f["verdict"], f["comment"], f["created_at"])


def run_demo(settings: dict[str, Any], run_date: str = "2026-11-08", product_id: str = "webneft",
             offline: bool = True, tickets: str | Path | None = None,
             db_path: str | None = None) -> tuple[Store, NightlyStats, RunResult]:
    product = load_product(product_id)
    out = Path(settings["out_dir"])
    store = Store(db_path or ":memory:")
    tracker = SqliteTracker(store, product["delivery"]["tracker_project"])
    seed_demo(store, tracker, product_id)
    chat, asr, vl = make_models(settings, offline)
    nightly = run_nightly(product, settings, store, JsonlTicketSource(tickets or DATA / "sample_tickets.jsonl"),
                          chat, asr, vl, run_date)
    toolbox = Toolbox(store, tracker, FileDigestSink(out), product, settings, run_date,
                      new_run_id(product_id, run_date))
    result = run_weekly(chat, toolbox, settings["agent"]["max_steps"], log_dir=out / "runs")
    return store, nightly, result


def evaluate(store: Store, result: RunResult, product_id: str = "webneft") -> dict[str, Any]:
    """Офлайн-оценка на золотой разметке: извлечение, кластеры, решения агента."""
    golden = {g["ticket_id"]: g for g in map(json.loads, (DATA / "golden.jsonl").read_text(encoding="utf-8")
                                             .splitlines()) if g}
    expected = json.loads((DATA / "expected_decisions.json").read_text(encoding="utf-8"))
    cards = store.cards(product_id)
    y_true = [golden[c.ticket_id]["type"] for c in cards]
    y_pred = [c.type for c in cards]
    truth = {t: g["problem_id"] for t, g in golden.items()}
    clusters = store.clusters(product_id)
    by_cluster = {c.id: cluster_to_problem(c.ticket_ids, truth) for c in clusters}
    predicted = {pid: "SKIP" for pid in expected}  # не попавшее в решения = не передано
    for d in result.decisions:
        pid = by_cluster.get(d["cluster_id"])
        if pid:
            predicted[pid] = d["decision"]
    for pid, exp in expected.items():
        if exp == "EXCLUDED" and predicted[pid] == "SKIP":
            predicted[pid] = "EXCLUDED"
    return {
        "type_macro_f1": round(macro_f1(y_true, y_pred), 3),
        "cluster_purity": round(purity([c.ticket_ids for c in clusters], truth), 3),
        **{k: round(v, 3) for k, v in decision_scores(predicted, expected).items()},
        "per_problem": {pid: {"expected": expected[pid], "predicted": predicted[pid]} for pid in expected},
    }


def run_nightly_only(settings: dict[str, Any], run_date: str, product_id: str, tickets: str | Path,
                     offline: bool) -> NightlyStats:
    """Боевой режим: ежедневно 01:00, постоянная БД (settings.db_path)."""
    product = load_product(product_id)
    store = Store(settings["db_path"])
    chat, asr, vl = make_models(settings, offline)
    return run_nightly(product, settings, store, JsonlTicketSource(tickets), chat, asr, vl, run_date)


def run_weekly_only(settings: dict[str, Any], run_date: str, product_id: str, offline: bool) -> RunResult:
    """Боевой режим: раз в неделю по каждому продукту, на кластерах из ночного конвейера."""
    product = load_product(product_id)
    store = Store(settings["db_path"])
    tracker = SqliteTracker(store, product["delivery"]["tracker_project"])
    chat, _, _ = make_models(settings, offline)
    out = Path(settings["out_dir"])
    toolbox = Toolbox(store, tracker, FileDigestSink(out), product, settings, run_date,
                      new_run_id(product_id, run_date))
    return run_weekly(chat, toolbox, settings["agent"]["max_steps"], log_dir=out / "runs")
