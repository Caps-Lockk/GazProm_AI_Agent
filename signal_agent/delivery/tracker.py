"""Сервис 7 (часть 1): адаптеры к трекерам задач.

Агент знает только интерфейс Tracker. Смена Jira на YouTrack или внутренний
трекер — новый адаптер, без правки агента и промпта.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


class Tracker(Protocol):
    def search(self, product: str, query: str, limit: int = 3) -> list[dict[str, Any]]: ...
    def create_draft(self, product: str, cluster_id: str, title: str, body: str, at: str) -> str: ...
    def find_by_cluster(self, cluster_id: str) -> str | None: ...
    def comment(self, issue_id: str, text: str, at: str) -> None: ...
    def get(self, issue_id: str) -> dict[str, Any] | None: ...


class SqliteTracker:
    """Трекер-заглушка поверх таблицы backlog: черновики создаются со статусом draft."""

    def __init__(self, store, project_key: str = "WN"):
        self.db = store.db
        self.key = project_key

    def seed(self, issues: list[dict[str, Any]]) -> None:
        for i in issues:
            self.db.execute("INSERT OR REPLACE INTO backlog VALUES (?,?,?,?,?,?,?,?)",
                            (i["issue_id"], i["product"], i["title"], i.get("body", ""), i["status"],
                             i.get("cluster_id"), i["created_at"], "[]"))
        self.db.commit()

    def search(self, product, query, limit=3):
        rows = [dict(r) for r in self.db.execute(
            "SELECT issue_id, title, status FROM backlog WHERE product = ?", (product,))]
        if not rows or not query.strip():
            return []
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), lowercase=True)
        X = vec.fit_transform([query] + [r["title"] for r in rows])
        scores = cosine_similarity(X[0], X[1:]).ravel()
        ranked = sorted(zip(rows, scores), key=lambda p: -p[1])[:limit]
        return [{**r, "score": round(float(s), 2)} for r, s in ranked if s >= 0.2]

    def create_draft(self, product, cluster_id, title, body, at):
        n = self.db.execute("SELECT COUNT(*) FROM backlog WHERE issue_id LIKE ?", (f"{self.key}-D%",)).fetchone()[0]
        issue_id = f"{self.key}-D{n + 1:03d}"
        self.db.execute("INSERT INTO backlog VALUES (?,?,?,?,?,?,?,?)",
                        (issue_id, product, title, body, "draft", cluster_id, at, "[]"))
        self.db.commit()
        return issue_id

    def find_by_cluster(self, cluster_id):
        r = self.db.execute("SELECT issue_id FROM backlog WHERE cluster_id = ? AND status = 'draft'",
                            (cluster_id,)).fetchone()
        return r[0] if r else None

    def comment(self, issue_id, text, at):
        r = self.db.execute("SELECT comments FROM backlog WHERE issue_id = ?", (issue_id,)).fetchone()
        comments = json.loads(r[0]) + [{"at": at, "text": text}]
        self.db.execute("UPDATE backlog SET comments = ? WHERE issue_id = ?",
                        (json.dumps(comments, ensure_ascii=False), issue_id))
        self.db.commit()

    def get(self, issue_id):
        r = self.db.execute("SELECT * FROM backlog WHERE issue_id = ?", (issue_id,)).fetchone()
        return dict(r) if r else None


class JiraTracker:  # pragma: no cover - нужен боевой контур
    """Боевой адаптер к Jira REST API v2 внутреннего контура (набросок)."""

    def __init__(self, base_url: str, token: str, project_key: str):
        self.base, self.token, self.key = base_url.rstrip("/"), token, project_key

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        import urllib.request
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(payload).encode() if payload else None,
                                     headers={"Authorization": f"Bearer {self.token}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"{}")

    def search(self, product, query, limit=3):
        jql = f'project = {self.key} AND text ~ "{query[:100]}" ORDER BY updated DESC'
        res = self._call("GET", f"/rest/api/2/search?maxResults={limit}&jql={jql}")
        return [{"issue_id": i["key"], "title": i["fields"]["summary"],
                 "status": i["fields"]["status"]["statusCategory"]["key"]} for i in res.get("issues", [])]

    def create_draft(self, product, cluster_id, title, body, at):
        res = self._call("POST", "/rest/api/2/issue", {"fields": {
            "project": {"key": self.key}, "summary": title, "description": body,
            "issuetype": {"name": "Task"}, "labels": ["signal-agent", cluster_id]}})
        return res["key"]

    def find_by_cluster(self, cluster_id):
        res = self._call("GET", f"/rest/api/2/search?maxResults=1&jql=labels={cluster_id}")
        issues = res.get("issues", [])
        return issues[0]["key"] if issues else None

    def comment(self, issue_id, text, at):
        self._call("POST", f"/rest/api/2/issue/{issue_id}/comment", {"body": text})

    def get(self, issue_id):
        return self._call("GET", f"/rest/api/2/issue/{issue_id}")
