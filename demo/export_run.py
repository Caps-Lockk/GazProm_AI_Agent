"""Выгружает реальный прогон демо в JSON для визуального проигрывателя demo/replay.html.

Запуск: python demo/export_run.py  → demo/run.json; затем python demo/build_replay.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from signal_agent.agent.tools import Toolbox  # noqa: E402
from signal_agent.app import DATA, run_demo  # noqa: E402
from signal_agent.config import load_settings  # noqa: E402
from signal_agent.pipeline.media import StubMedia, ticket_text  # noqa: E402
from signal_agent.pipeline.pii import mask  # noqa: E402
from signal_agent.models import Ticket  # noqa: E402


def main() -> None:
    settings = load_settings()
    settings["out_dir"] = tempfile.mkdtemp()
    store, nightly, result = run_demo(settings)
    media = StubMedia(DATA / "media_stub.json")
    tickets = [Ticket.from_dict(json.loads(l)) for l in (DATA / "sample_tickets.jsonl").read_text("utf-8").splitlines()]
    cards = {c.ticket_id: c for c in store.cards("webneft")}
    tb = Toolbox(store, None, None, __import__("signal_agent.config", fromlist=["x"]).load_product("webneft"),
                 settings, "2026-11-08", "x")
    clusters = []
    for c in store.clusters("webneft"):
        s = tb._stats(c)
        clusters.append({"id": c.id, "label": c.label, "type": c.type, "module": c.module, "size": len(c.ticket_ids),
                         "tickets_period": s["tickets"], "clients": s["clients"], "last_7d": s["last_7d"],
                         "prev_7d": s["prev_7d"], "incident": c.type == "incident" or s["critical"],
                         "trend": [w["tickets"] for w in tb.get_cluster_trend(c.id)], "ticket_ids": c.ticket_ids})
    out_tickets = []
    for t in tickets:
        raw = ticket_text(t, media, media)
        out_tickets.append({"id": t.id, "channel": t.channel, "date": t.created_at, "raw": raw, "masked": mask(raw),
                            "has_image": bool(t.attachments), "card": cards[t.id].to_dict()})
    log_path = Path(settings["out_dir"]) / "runs" / f"{result.run_id}.jsonl"
    steps = [json.loads(l) for l in log_path.read_text("utf-8").splitlines()]
    backlog = [dict(r) for r in store.db.execute("SELECT * FROM backlog ORDER BY issue_id")]
    for b in backlog:
        b["comments"] = json.loads(b["comments"])
    digest = Path(result.digest_path).read_text("utf-8")
    decisions = [{k: d[k] for k in ("cluster_id", "decision", "issue_id", "reason")} for d in result.decisions]
    data = {"run_id": result.run_id, "run_date": "2026-11-08", "nightly": nightly.__dict__, "tickets": out_tickets,
            "clusters": clusters, "steps": steps, "decisions": decisions, "backlog": backlog, "digest": digest}
    (ROOT / "demo" / "run.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print(f"{len(out_tickets)} тикетов, {len(clusters)} кластеров, {len(steps)} вызовов инструментов")


if __name__ == "__main__":
    main()
