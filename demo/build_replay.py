"""Собирает самодостаточную страницу demo/replay.html из demo/run.json."""
from pathlib import Path

HERE = Path(__file__).parent
html = (HERE / "replay_template.html").read_text("utf-8")
data = (HERE / "run.json").read_text("utf-8").replace("</", "<\\/")
(HERE / "replay.html").write_text(html.replace("__DATA__", data), encoding="utf-8")
print("demo/replay.html готов")
