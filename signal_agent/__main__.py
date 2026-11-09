"""CLI: python -m signal_agent demo | eval | nightly | weekly

  demo    — ночной конвейер + недельный агент на синтетических обращениях «Вебнефти»
  eval    — то же + офлайн-оценка на золотой разметке (выход 1, если пороги не пройдены)
  nightly — только ночной конвейер, постоянная БД (для планировщика)
  weekly  — только недельный прогон агента по продукту (для планировщика)
Флаг --online переключает с офлайн-модели на внутренние Qwen (адреса в config/settings.yaml).
"""
from __future__ import annotations

import argparse
import json
import sys

from .app import evaluate, run_demo, run_nightly_only, run_weekly_only
from .config import load_settings

THRESHOLDS = {"precision": 0.75, "recall": 0.85, "type_macro_f1": 0.80, "cluster_purity": 0.80}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="signal_agent")
    ap.add_argument("command", choices=["demo", "eval", "nightly", "weekly"])
    ap.add_argument("--product", default="webneft")
    ap.add_argument("--date", default="2026-11-08", help="дата прогона")
    ap.add_argument("--online", action="store_true", help="использовать внутренние Qwen вместо офлайн-модели")
    ap.add_argument("--tickets", help="JSONL с обращениями (по умолчанию data/sample_tickets.jsonl)")
    ap.add_argument("--db", help="путь к SQLite (по умолчанию в памяти)")
    args = ap.parse_args(argv)

    settings = load_settings()
    if args.command == "nightly":
        st = run_nightly_only(settings, args.date, args.product, args.tickets or "data/sample_tickets.jsonl",
                              offline=not args.online)
        print(f"Ночной конвейер: {st.ingested} новых тикетов, {st.carded} карточек, {st.clusters} кластеров")
        return 0
    if args.command == "weekly":
        res = run_weekly_only(settings, args.date, args.product, offline=not args.online)
        print(f"Агент: {res.steps} шагов, решений {len(res.decisions)}, дайджест {res.digest_path}")
        return 0
    store, nightly, result = run_demo(settings, args.date, offline=not args.online,
                                      tickets=args.tickets, db_path=args.db)
    print(f"Ночной конвейер: {nightly.ingested} тикетов, {nightly.carded} карточек "
          f"({nightly.needs_review} на проверку), {nightly.clusters} кластеров")
    print(f"Агент: {result.steps} шагов, прогон {result.run_id}")
    for d in result.decisions:
        title = json.loads(d["payload"]).get("title", "") if d["payload"] else ""
        print(f"  {d['decision']:<6} {d['issue_id'] or '':<8} {title or d['reason']}")
    print(f"Дайджест: {result.digest_path}")

    if args.command == "eval":
        report = evaluate(store, result)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        failed = [k for k, v in THRESHOLDS.items() if report[k] < v]
        if failed:
            print("Не пройдены пороги:", ", ".join(failed))
            return 1
        print("Все пороги приёмки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
