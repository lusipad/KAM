from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

from adapters.github import GitHubAdapter
from config import settings
from runtime_paths import bundle_root
from scripts.github_monitor_support import (
    ensure_repo_workspace,
    read_json,
    resolve_github_token,
    safe_repo_slug,
    write_json,
)
from services.source_tasks import (
    GITHUB_ISSUE_SOURCE_KIND,
    build_github_issue_task_description,
    build_github_issue_task_title,
)
from services.task_autodrive import GlobalAutoDriveService


GITHUB_ISSUE_MONITORS_FILENAME = "github-issue-monitors.json"
GITHUB_ISSUE_MONITORS_DIRNAME = "github-issue-monitors"
GITHUB_ISSUE_MONITOR_DEFAULT_STATUS = "idle"
GITHUB_ISSUE_MONITOR_DEFAULT_SUMMARY = "监控已注册，等待下一轮轮询。"


@dataclass(frozen=True)
class IssueMonitorConfig:
    repo: str
    repo_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo": self.repo,
            "repoPath": self.repo_path,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass
class _IssueMonitorRuntimeState:
    tasks: dict[str, asyncio.Task[None]] = field(default_factory=dict)
    locks: dict[str, asyncio.Lock] = field(default_factory=dict)
    summaries: dict[str, dict[str, Any]] = field(default_factory=dict)


_STATE = _IssueMonitorRuntimeState()


def _repo_key(repo: str) -> str:
    return repo.strip().lower()


def _config_path() -> Path:
    return settings.storage_dir / GITHUB_ISSUE_MONITORS_FILENAME


def _monitor_root(repo: str) -> Path:
    return settings.storage_dir / GITHUB_ISSUE_MONITORS_DIRNAME / safe_repo_slug(repo)


def _monitor_state_path(repo: str) -> Path:
    return _monitor_root(repo) / "state.json"


def _monitor_summary_path(repo: str) -> Path:
    return _monitor_root(repo) / "last-run.json"


def _monitor_storage_root() -> Path:
    return settings.storage_dir / GITHUB_ISSUE_MONITORS_DIRNAME


def _current_timestamp() -> str:
    from models import now

    return now().isoformat()


def _normalize_repo(repo: str) -> str:
    normalized = repo.strip()
    if not normalized or "/" not in normalized:
        raise ValueError("repo 必须是 owner/name 形式。")
    owner, name = normalized.split("/", 1)
    owner = owner.strip()
    name = name.strip()
    if not owner or not name:
        raise ValueError("repo 必须是 owner/name 形式。")
    return f"{owner}/{name}"


def _normalize_repo_path(repo_path: str | None) -> str | None:
    if repo_path is None:
        return None
    normalized = repo_path.strip()
    return normalized or None


def _load_configs() -> list[IssueMonitorConfig]:
    payload = read_json(_config_path()) or {}
    items = payload.get("monitors")
    if not isinstance(items, list):
        return []
    configs: list[IssueMonitorConfig] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        repo_value = item.get("repo")
        if not isinstance(repo_value, str):
            continue
        try:
            repo = _normalize_repo(repo_value)
        except ValueError:
            continue
        key = _repo_key(repo)
        if key in seen:
            continue
        seen.add(key)
        configs.append(
            IssueMonitorConfig(
                repo=repo,
                repo_path=_normalize_repo_path(item.get("repoPath")),
                created_at=item.get("createdAt") if isinstance(item.get("createdAt"), str) else None,
                updated_at=item.get("updatedAt") if isinstance(item.get("updatedAt"), str) else None,
            )
        )
    return configs


def _persist_configs(configs: list[IssueMonitorConfig]) -> None:
    payload = {"monitors": [item.to_dict() for item in configs]}
    write_json(_config_path(), payload)


def _find_config(repo: str) -> IssueMonitorConfig | None:
    repo_key = _repo_key(repo)
    for item in _load_configs():
        if _repo_key(item.repo) == repo_key:
            return item
    return None


def _runtime_lock(repo: str) -> asyncio.Lock:
    key = _repo_key(repo)
    lock = _STATE.locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _STATE.locks[key] = lock
    return lock


def _runtime_summary(repo: str) -> dict[str, Any]:
    key = _repo_key(repo)
    summary = _STATE.summaries.get(key)
    if summary is not None:
        return dict(summary)
    file_summary = read_json(_monitor_summary_path(repo))
    if isinstance(file_summary, dict):
        _STATE.summaries[key] = dict(file_summary)
        return dict(file_summary)
    return {
        "status": GITHUB_ISSUE_MONITOR_DEFAULT_STATUS,
        "message": GITHUB_ISSUE_MONITOR_DEFAULT_SUMMARY,
    }


def _monitor_record(config: IssueMonitorConfig) -> dict[str, Any]:
    summary = _runtime_summary(config.repo)
    key = _repo_key(config.repo)
    running = key in _STATE.tasks and not _STATE.tasks[key].done()
    return {
        "repo": config.repo,
        "repoPath": config.repo_path,
        "running": running,
        "status": summary.get("status") or GITHUB_ISSUE_MONITOR_DEFAULT_STATUS,
        "summary": summary.get("message") or GITHUB_ISSUE_MONITOR_DEFAULT_SUMMARY,
        "lastCheckedAt": summary.get("checkedAt"),
        "issueCount": summary.get("issueCount"),
        "changedIssueCount": summary.get("changedIssueCount"),
        "taskIds": summary.get("taskIds") if isinstance(summary.get("taskIds"), list) else [],
    }


def list_issue_monitors() -> list[dict[str, Any]]:
    return [_monitor_record(item) for item in _load_configs()]


def _issue_comments(issue: dict[str, Any]) -> list[dict[str, Any]]:
    raw_comments = issue.get("issue_comments")
    if not isinstance(raw_comments, list):
        return []
    return [dict(item) for item in raw_comments if isinstance(item, dict)]


def _build_harness_task_payload(
    *,
    repo: str,
    workspace: Path,
    issue: dict[str, Any],
    create_run: dict[str, Any],
) -> dict[str, Any]:
    issue_number = int(issue["number"])
    issue_title = str(issue.get("title") or "").strip()
    issue_body = str(issue.get("body") or "").strip()
    issue_comments = _issue_comments(issue)
    source_kind = GITHUB_ISSUE_SOURCE_KIND
    source_dedup_key = f"{source_kind}:{repo}:{issue_number}"
    title = build_github_issue_task_title(repo, issue_number, issue_title)
    description = build_github_issue_task_description(repo, issue_number, issue_title, issue_body, issue_comments)

    refs: list[dict[str, Any]] = []
    issue_url = issue.get("html_url")
    if isinstance(issue_url, str) and issue_url.strip():
        refs.append(
            {
                "kind": "url",
                "label": f"{repo} Issue #{issue_number}",
                "value": issue_url.strip(),
                "metadata": {"intakeSourceKind": source_kind},
            }
        )

    for item in issue_comments[:5]:
        comment_url = item.get("html_url") or item.get("url")
        comment_id = item.get("id")
        if isinstance(comment_url, str) and comment_url.strip():
            refs.append(
                {
                    "kind": "url",
                    "label": f"Issue comment #{comment_id}",
                    "value": comment_url.strip(),
                    "metadata": {"commentId": comment_id, "intakeSourceKind": source_kind},
                }
            )

    params = create_run.get("params", {})
    metadata: dict[str, Any] = {
        "recommendedPrompt": params.get("task"),
        "recommendedAgent": params.get("agent", "codex"),
        "sourceKind": source_kind,
        "sourceDedupKey": source_dedup_key,
        "sourceRepo": repo,
        "sourceIssueNumber": issue_number,
        "sourceIssueTitle": issue_title,
        "sourceIssueBody": issue_body,
        "sourceIssueComments": issue_comments,
        "sourceMeta": {
            "state": issue.get("state"),
            "user": issue.get("user"),
            "labels": issue.get("labels") if isinstance(issue.get("labels"), list) else [],
            "html_url": issue_url,
            "commentsCount": issue.get("comments_count"),
            "created_at": issue.get("created_at"),
            "updated_at": issue.get("updated_at"),
        },
    }

    return {
        "title": title,
        "description": description,
        "repoPath": str(workspace),
        "status": "open",
        "priority": "high",
        "labels": ["github", "issue"],
        "metadata": metadata,
        "refs": refs,
    }


async def _enqueue_task_via_app(app: FastAPI, payload: dict[str, Any]) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://kam.local") as client:
        response = await client.post("/api/tasks", json=payload, timeout=30.0)
        response.raise_for_status()
        return response.json()


async def run_issue_monitor_once(repo: str, app: FastAPI) -> dict[str, Any]:
    config = _find_config(repo)
    if config is None:
        raise ValueError("issue monitor 未注册。")

    lock = _runtime_lock(config.repo)
    async with lock:
        state_path = _monitor_state_path(config.repo)
        summary_path = _monitor_summary_path(config.repo)
        workspace = ensure_repo_workspace(config.repo, _monitor_root(config.repo) / "repo", config.repo_path)
        summary: dict[str, Any] = {
            "checkedAt": _current_timestamp(),
            "repo": config.repo,
            "stateFile": str(state_path),
            "workspace": str(workspace),
        }
        try:
            resolve_github_token(config.repo, project_root=bundle_root())
            previous_state = read_json(state_path)
            adapter = GitHubAdapter()
            current_state = await adapter.fetch({"repo": config.repo, "watch": "issues"})
            changes = adapter.diff(previous_state, current_state)

            summary["issueCount"] = len(current_state.get("items", []))
            summary["changedIssueCount"] = len(changes.get("issues", []))
            summary["meta"] = current_state.get("meta", {})

            current_error = current_state.get("meta", {}).get("error")
            if current_error:
                summary["status"] = "source-error"
                summary["message"] = current_error
                write_json(summary_path, summary)
                _STATE.summaries[_repo_key(config.repo)] = dict(summary)
                return summary

            changed_issues = [
                item
                for item in changes.get("issues", [])
                if isinstance(item, dict) and isinstance(item.get("number"), int)
            ]
            if not changed_issues:
                summary["status"] = "idle"
                summary["message"] = "没有新的 GitHub issue 变化。"
                write_json(state_path, current_state)
                write_json(summary_path, summary)
                _STATE.summaries[_repo_key(config.repo)] = dict(summary)
                return summary

            actions = adapter.recommended_actions(
                {"name": f"{config.repo} issue 监控", "config": {"repo": config.repo, "watch": "issues"}},
                changes,
            )
            issues_by_number = {int(item["number"]): item for item in changed_issues}
            issue_actions: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
            for action in actions:
                if action.get("kind") != "create_run":
                    continue
                params = action.get("params", {})
                issue_number = params.get("sourceIssueNumber")
                if not isinstance(issue_number, int):
                    continue
                issue = issues_by_number.get(issue_number)
                if issue is None:
                    continue
                issue_actions.append((issue_number, issue, action))

            if not issue_actions:
                summary["status"] = "noop"
                summary["message"] = "检测到 issue 更新，但没有可执行的自动动作。"
                write_json(state_path, current_state)
                write_json(summary_path, summary)
                _STATE.summaries[_repo_key(config.repo)] = dict(summary)
                return summary

            task_ids: list[str] = []
            issue_numbers: list[int] = []
            for issue_number, issue, create_run in issue_actions:
                task_payload = _build_harness_task_payload(
                    repo=config.repo,
                    workspace=workspace,
                    issue=issue,
                    create_run=create_run,
                )
                created_task = await _enqueue_task_via_app(app, task_payload)
                task_id = created_task.get("id")
                if isinstance(task_id, str) and task_id.strip():
                    task_ids.append(task_id.strip())
                issue_numbers.append(issue_number)

            write_json(state_path, current_state)
            summary["taskMode"] = "harness_queue"
            summary["issueNumbers"] = issue_numbers
            summary["taskIds"] = task_ids
            summary["status"] = "enqueued"
            summary["message"] = f"检测到 {len(issue_numbers)} 个 GitHub issue 更新，已同步到 KAM 任务池。"
            summary["autodrive"] = (await GlobalAutoDriveService().start()).to_dict()
            write_json(summary_path, summary)
            _STATE.summaries[_repo_key(config.repo)] = dict(summary)
            return summary
        except Exception as exc:
            summary["status"] = "failed"
            summary["message"] = f"{type(exc).__name__}: {exc}"
            write_json(summary_path, summary)
            _STATE.summaries[_repo_key(config.repo)] = dict(summary)
            return summary


async def _run_issue_monitor_loop(repo: str, app: FastAPI, *, initial_delay_seconds: float) -> None:
    if initial_delay_seconds > 0:
        await asyncio.sleep(initial_delay_seconds)
    while True:
        config = _find_config(repo)
        if config is None:
            return
        await run_issue_monitor_once(config.repo, app)
        await asyncio.sleep(float(settings.github_issue_monitor_poll_seconds))


def schedule_issue_monitor_runtime(repo: str, app: FastAPI, *, initial_delay_seconds: float) -> bool:
    key = _repo_key(repo)
    current = _STATE.tasks.get(key)
    if current is not None and not current.done():
        return False
    background_task = asyncio.create_task(_run_issue_monitor_loop(repo, app, initial_delay_seconds=initial_delay_seconds))
    _STATE.tasks[key] = background_task

    def _cleanup(done_task: asyncio.Task[None]) -> None:
        current_task = _STATE.tasks.get(key)
        if current_task is done_task:
            _STATE.tasks.pop(key, None)

    background_task.add_done_callback(_cleanup)
    return True


async def upsert_issue_monitor(
    repo: str,
    repo_path: str | None,
    *,
    app: FastAPI | None,
    run_now: bool,
) -> dict[str, Any]:
    normalized_repo = _normalize_repo(repo)
    normalized_repo_path = _normalize_repo_path(repo_path)
    configs = _load_configs()
    timestamp = _current_timestamp()
    next_configs: list[IssueMonitorConfig] = []
    matched = False
    for item in configs:
        if _repo_key(item.repo) != _repo_key(normalized_repo):
            next_configs.append(item)
            continue
        matched = True
        next_configs.append(
            IssueMonitorConfig(
                repo=normalized_repo,
                repo_path=normalized_repo_path,
                created_at=item.created_at or timestamp,
                updated_at=timestamp,
            )
        )
    if not matched:
        next_configs.append(
            IssueMonitorConfig(
                repo=normalized_repo,
                repo_path=normalized_repo_path,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    _persist_configs(next_configs)

    if app is not None:
        if run_now:
            await run_issue_monitor_once(normalized_repo, app)
            schedule_issue_monitor_runtime(
                normalized_repo,
                app,
                initial_delay_seconds=float(settings.github_issue_monitor_poll_seconds),
            )
        else:
            schedule_issue_monitor_runtime(normalized_repo, app, initial_delay_seconds=1.0)

    config = _find_config(normalized_repo)
    if config is None:
        raise RuntimeError("issue monitor 保存失败。")
    return _monitor_record(config)


async def remove_issue_monitor(repo: str) -> bool:
    normalized_repo = _normalize_repo(repo)
    remaining = [item for item in _load_configs() if _repo_key(item.repo) != _repo_key(normalized_repo)]
    existed = len(remaining) != len(_load_configs())
    _persist_configs(remaining)
    key = _repo_key(normalized_repo)
    background_task = _STATE.tasks.pop(key, None)
    if background_task is not None and not background_task.done():
        background_task.cancel()
        await asyncio.gather(background_task, return_exceptions=True)
    _STATE.summaries.pop(key, None)
    if not remaining:
        _config_path().unlink(missing_ok=True)
    return existed


async def recover_github_issue_monitor_runtime_state(app: FastAPI) -> None:
    if settings.is_test_env:
        return
    for config in _load_configs():
        schedule_issue_monitor_runtime(config.repo, app, initial_delay_seconds=1.0)


async def shutdown_github_issue_monitor_runtime() -> None:
    tasks = [task for task in _STATE.tasks.values() if not task.done()]
    _STATE.tasks.clear()
    if not tasks:
        return
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def reset_github_issue_monitor_runtime_state(*, clear_persistence: bool = False) -> None:
    for task in list(_STATE.tasks.values()):
        if not task.done():
            task.cancel()
    _STATE.tasks.clear()
    _STATE.locks.clear()
    _STATE.summaries.clear()
    if clear_persistence:
        _config_path().unlink(missing_ok=True)
        shutil.rmtree(_monitor_storage_root(), ignore_errors=True)
