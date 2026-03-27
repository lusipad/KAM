from __future__ import annotations

from typing import Any

from ghapi.all import GhApi

from config import settings


def _split_repo(repo: str) -> tuple[str, str]:
    owner, name = repo.split("/", 1)
    return owner, name


class GitHubPRAdapter:
    def __init__(self) -> None:
        self._api = GhApi(token=settings.github_token) if settings.github_token else None

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        if self._api is None:
            return {"items": [], "review_comments": [], "meta": {"error": "missing_github_token"}}

        repo = config["repo"]
        owner, name = _split_repo(repo)
        watch = config.get("watch", "assigned_prs")
        number = config.get("number")

        if watch == "review_comments" and number:
            comments = list(self._api.pulls.list_review_comments(owner, name, number))
            items = [
                {
                    "id": item.id,
                    "body": item.body or "",
                    "path": item.path,
                    "line": getattr(item, "line", None),
                    "user": getattr(item.user, "login", "unknown"),
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "pull_number": number,
                    "html_url": item.html_url,
                }
                for item in comments
            ]
            return {"items": items, "review_comments": items, "meta": {"repo": repo, "watch": watch}}

        pulls = list(self._api.pulls.list(owner, name, state="open"))
        items = []
        current_user = config.get("filter_user")
        for pull in pulls:
            assignees = [assignee.login for assignee in getattr(pull, "assignees", [])]
            if current_user and current_user != "me" and current_user not in assignees:
                continue
            items.append(
                {
                    "id": pull.id,
                    "number": pull.number,
                    "title": pull.title,
                    "state": pull.state,
                    "updated_at": pull.updated_at,
                    "draft": bool(getattr(pull, "draft", False)),
                    "user": getattr(pull.user, "login", "unknown"),
                    "html_url": pull.html_url,
                }
            )
        return {"items": items, "review_comments": [], "meta": {"repo": repo, "watch": watch}}

    def diff(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
        previous_items = {str(item["id"]): item for item in (previous or {}).get("items", [])}
        created = []
        updated = []
        for item in current.get("items", []):
            item_id = str(item["id"])
            old_item = previous_items.get(item_id)
            if old_item is None:
                created.append(item)
            elif old_item.get("updated_at") != item.get("updated_at"):
                updated.append(item)
        return {"created": created, "updated": updated, "review_comments": current.get("review_comments", [])}

    def recommended_actions(self, watcher: dict[str, Any], changes: dict[str, Any]) -> list[dict[str, Any]]:
        if changes.get("review_comments"):
            return [
                {
                    "label": "Analyze comments",
                    "kind": "create_run",
                    "params": {
                        "agent": "codex",
                        "task": f"Analyze new PR review comments for {watcher['name']} and prepare fixes or replies.",
                    },
                }
            ]
        return []

    async def perform(self, action: dict[str, Any]) -> dict[str, Any]:
        if self._api is None:
            return {"ok": False, "error": "missing_github_token"}

        kind = action.get("kind")
        params = action.get("params", {})
        if kind == "reply_review_comment":
            owner, repo = _split_repo(params["repo"])
            self._api.pulls.create_reply_for_review_comment(
                owner,
                repo,
                params["pull_number"],
                params["comment_id"],
                body=params["body"],
            )
            return {"ok": True}

        if kind == "rerun_workflow":
            owner, repo = _split_repo(params["repo"])
            self._api.actions.re_run_workflow(owner, repo, params["run_id"])
            return {"ok": True}

        return {"ok": False, "error": f"unsupported_action:{kind}"}
