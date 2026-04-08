from __future__ import annotations

import json
import subprocess
from typing import Any

from ghapi.all import GhApi

from config import settings
from services.source_tasks import build_github_issue_task_prompt, build_github_review_task_prompt


def _split_repo(repo: str) -> tuple[str, str]:
    owner, name = repo.split("/", 1)
    return owner, name


def _load_git_credential_token() -> str:
    try:
        completed = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return ""
    if completed.returncode != 0:
        return ""
    for line in completed.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def _resolve_github_token() -> str:
    return settings.github_token or _load_git_credential_token()


def _github_issue_comment_record(item: Any) -> dict[str, Any]:
    return {
        "id": item.id,
        "body": item.body or "",
        "user": getattr(item.user, "login", "unknown"),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "html_url": item.html_url,
    }


def _github_issue_record(item: Any, issue_comments: list[dict[str, Any]]) -> dict[str, Any]:
    labels: list[str] = []
    for label in getattr(item, "labels", []) or []:
        name = getattr(label, "name", None)
        if isinstance(name, str) and name.strip():
            labels.append(name.strip())
    return {
        "id": item.id,
        "number": item.number,
        "title": item.title or "",
        "state": item.state,
        "updated_at": item.updated_at,
        "created_at": item.created_at,
        "user": getattr(item.user, "login", "unknown"),
        "html_url": item.html_url,
        "body": item.body or "",
        "labels": labels,
        "comments_count": len(issue_comments),
        "issue_comments": issue_comments,
    }


class GitHubAdapter:
    def __init__(self) -> None:
        self._token = _resolve_github_token()
        self._api = GhApi(token=self._token) if self._token else GhApi()

    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        repo = config["repo"]
        owner, name = _split_repo(repo)
        watch = config.get("watch", "assigned_prs")
        number = config.get("number")

        if watch == "review_comments" and number:
            meta = {"repo": repo, "watch": watch, "number": number}
            try:
                pull = self._api.pulls.get(owner, name, number)
                head = getattr(pull, "head", None)
                head_repo = getattr(head, "repo", None)
                base = getattr(pull, "base", None)
                meta.update(
                    {
                        "pullUrl": getattr(pull, "html_url", None),
                        "title": getattr(pull, "title", None),
                        "state": getattr(pull, "state", None),
                        "draft": bool(getattr(pull, "draft", False)),
                        "headRef": getattr(head, "ref", None),
                        "headSha": getattr(head, "sha", None),
                        "headRepo": getattr(head_repo, "full_name", repo) if head_repo is not None else repo,
                        "baseRef": getattr(base, "ref", None),
                    }
                )
                comments = list(self._api.pulls.list_review_comments(owner, name, number))
            except Exception as exc:
                return {
                    "items": [],
                    "review_comments": [],
                    "issues": [],
                    "meta": {**meta, "error": f"{type(exc).__name__}: {exc}"},
                }

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
            return {"items": items, "review_comments": items, "issues": [], "meta": meta}

        if watch == "issues":
            meta = {"repo": repo, "watch": watch}
            try:
                issues = list(self._api.issues.list_for_repo(owner, name, state="open", sort="updated", direction="desc"))
                items: list[dict[str, Any]] = []
                for issue in issues:
                    if getattr(issue, "pull_request", None) is not None:
                        continue
                    issue_comments = [
                        _github_issue_comment_record(item)
                        for item in self._api.issues.list_comments(owner, name, issue.number)
                    ]
                    items.append(_github_issue_record(issue, issue_comments))
            except Exception as exc:
                return {
                    "items": [],
                    "review_comments": [],
                    "issues": [],
                    "meta": {**meta, "error": f"{type(exc).__name__}: {exc}"},
                }
            return {"items": items, "review_comments": [], "issues": items, "meta": meta}

        try:
            pulls = list(self._api.pulls.list(owner, name, state="open"))
        except Exception as exc:
            return {
                "items": [],
                "review_comments": [],
                "issues": [],
                "meta": {"repo": repo, "watch": watch, "error": f"{type(exc).__name__}: {exc}"},
            }

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
        return {"items": items, "review_comments": [], "issues": [], "meta": {"repo": repo, "watch": watch}}

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

        previous_meta = (previous or {}).get("meta", {})
        current_meta = current.get("meta", {})
        errors = []
        current_error = current_meta.get("error")
        if current_error and current_error != previous_meta.get("error"):
            errors.append(
                {
                    "repo": current_meta.get("repo"),
                    "watch": current_meta.get("watch"),
                    "number": current_meta.get("number"),
                    "message": current_error,
                }
            )

        review_comments: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        watch = current_meta.get("watch")
        if watch == "review_comments":
            review_comments = [*created, *updated]
        if watch == "issues":
            issues = [*created, *updated]

        return {
            "created": created,
            "updated": updated,
            "review_comments": review_comments,
            "issues": issues,
            "errors": errors,
            "meta": current_meta,
        }

    def recommended_actions(self, watcher: dict[str, Any], changes: dict[str, Any]) -> list[dict[str, Any]]:
        if changes.get("review_comments"):
            config = watcher.get("config", {})
            repo = config.get("repo", "owner/repo")
            number = config.get("number")
            changed_comments = [
                {
                    "id": item.get("id"),
                    "path": item.get("path"),
                    "line": item.get("line"),
                    "user": item.get("user"),
                    "url": item.get("html_url"),
                    "body": " ".join(str(item.get("body", "")).split())[:180],
                }
                for item in changes["review_comments"]
            ]
            return [
                {
                    "label": "处理评审",
                    "kind": "create_run",
                    "params": {
                        "agent": "codex",
                        "task": build_github_review_task_prompt(repo, number, changed_comments),
                        "sourcePullNumber": number,
                        "initialArtifacts": [
                            {
                                "type": "github_pr_context",
                                "content": json.dumps(
                                    {
                                        "watcherName": watcher.get("name"),
                                        "repo": repo,
                                        "number": number,
                                        "watch": config.get("watch", "review_comments"),
                                        "meta": changes.get("meta", {}),
                                    },
                                    ensure_ascii=False,
                                    indent=2,
                                ),
                                "metadata": {"repo": repo, "number": number},
                            },
                            {
                                "type": "github_review_comments",
                                "content": json.dumps(changes["review_comments"], ensure_ascii=False, indent=2),
                                "metadata": {"count": len(changes["review_comments"])},
                            },
                        ],
                    },
                }
            ]

        if changes.get("issues"):
            config = watcher.get("config", {})
            repo = config.get("repo", "owner/repo")
            actions: list[dict[str, Any]] = []
            for issue in changes["issues"]:
                issue_number = issue.get("number")
                if not isinstance(issue_number, int):
                    continue
                issue_title = " ".join(str(issue.get("title", "")).split())
                issue_comments = issue.get("issue_comments") if isinstance(issue.get("issue_comments"), list) else []
                actions.append(
                    {
                        "label": f"处理 Issue #{issue_number}",
                        "kind": "create_run",
                        "params": {
                            "agent": "codex",
                            "task": build_github_issue_task_prompt(
                                repo,
                                issue_number,
                                issue_title,
                                issue.get("body"),
                                issue_comments,
                            ),
                            "sourceIssueNumber": issue_number,
                            "initialArtifacts": [
                                {
                                    "type": "github_issue_context",
                                    "content": json.dumps(
                                        {
                                            "watcherName": watcher.get("name"),
                                            "repo": repo,
                                            "number": issue_number,
                                            "watch": config.get("watch", "issues"),
                                            "issue": {
                                                "title": issue.get("title"),
                                                "body": issue.get("body"),
                                                "labels": issue.get("labels"),
                                                "html_url": issue.get("html_url"),
                                                "user": issue.get("user"),
                                                "updated_at": issue.get("updated_at"),
                                            },
                                        },
                                        ensure_ascii=False,
                                        indent=2,
                                    ),
                                    "metadata": {"repo": repo, "number": issue_number},
                                },
                                {
                                    "type": "github_issue_comments",
                                    "content": json.dumps(issue_comments, ensure_ascii=False, indent=2),
                                    "metadata": {"count": len(issue_comments)},
                                },
                            ],
                        },
                    }
                )
            return actions
        return []

    async def perform(self, action: dict[str, Any]) -> dict[str, Any]:
        if not self._token:
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


GitHubPRAdapter = GitHubAdapter
