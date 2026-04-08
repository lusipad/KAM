#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from adapters.github import GitHubAdapter  # noqa: E402
from github_monitor_support import (  # noqa: E402
    FileLock,
    build_summary,
    ensure_repo_workspace,
    enqueue_task_to_harness,
    read_json,
    resolve_github_token,
    safe_repo_slug,
    start_harness_global_autodrive,
    write_json,
)
from services.source_tasks import (  # noqa: E402
    GITHUB_ISSUE_SOURCE_KIND,
    build_github_issue_task_description,
    build_github_issue_task_title,
)


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor GitHub issues and enqueue them into the KAM task pool.")
    parser.add_argument("--repo", required=True, help="GitHub repo, e.g. lusipad/KAM")
    parser.add_argument("--kam-url", default=os.environ.get("KAM_API_URL", "http://127.0.0.1:8000/api"))
    parser.add_argument("--repo-path", default="", help="Optional local repo path to use as the task repoPath instead of the output clone")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    monitor_root = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "output" / "issue-monitor" / safe_repo_slug(args.repo)
    default_workspace = monitor_root / "repo"
    state_path = monitor_root / "state.json"
    summary_path = monitor_root / "last-run.json"
    lock_path = monitor_root / "monitor.lock"
    summary: dict[str, Any] = {
        "repo": args.repo,
        "stateFile": str(state_path),
        "workspace": str(default_workspace),
    }

    try:
        with FileLock(lock_path):
            workspace = ensure_repo_workspace(args.repo, default_workspace, args.repo_path)
            summary = build_summary(repo=args.repo, state_path=state_path, workspace=workspace)
            resolve_github_token(args.repo, project_root=PROJECT_ROOT)

            config = {
                "repo": args.repo,
                "watch": "issues",
            }
            previous_state = read_json(state_path)
            adapter = GitHubAdapter()
            current_state = asyncio.run(adapter.fetch(config))
            changes = adapter.diff(previous_state, current_state)

            summary["issueCount"] = len(current_state.get("items", []))
            summary["changedIssueCount"] = len(changes.get("issues", []))
            summary["meta"] = current_state.get("meta", {})

            current_error = current_state.get("meta", {}).get("error")
            if current_error:
                summary["status"] = "source-error"
                summary["message"] = current_error
                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 1

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
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            actions = adapter.recommended_actions(
                {"name": f"{args.repo} issue 监控", "config": config},
                changes,
            )
            issues_by_number = {int(item["number"]): item for item in changed_issues}
            issue_actions: list[tuple[int, dict[str, Any]]] = []
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
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            if args.dry_run:
                summary["status"] = "dry-run"
                summary["taskMode"] = "harness_queue"
                summary["enqueuePayloads"] = [
                    _build_harness_task_payload(repo=args.repo, workspace=workspace, issue=issue, create_run=create_run)
                    for _, issue, create_run in issue_actions
                ]
                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            if not args.kam_url.strip():
                raise RuntimeError("缺少 KAM API 地址，请传入 --kam-url。")

            task_ids: list[str] = []
            issue_numbers: list[int] = []
            for issue_number, issue, create_run in issue_actions:
                task_payload = _build_harness_task_payload(
                    repo=args.repo,
                    workspace=workspace,
                    issue=issue,
                    create_run=create_run,
                )
                created_task = enqueue_task_to_harness(args.kam_url, task_payload)
                task_id = created_task.get("id")
                if isinstance(task_id, str) and task_id.strip():
                    task_ids.append(task_id.strip())
                issue_numbers.append(issue_number)

            summary["taskMode"] = "harness_queue"
            summary["issueNumbers"] = issue_numbers
            summary["taskIds"] = task_ids
            summary["status"] = "enqueued"
            summary["message"] = f"检测到 {len(issue_numbers)} 个 GitHub issue 更新，已同步到 KAM 任务池。"
            write_json(state_path, current_state)
            try:
                summary["autodrive"] = start_harness_global_autodrive(args.kam_url)
            except Exception as autodrive_exc:
                summary["status"] = "enqueued-with-autodrive-error"
                summary["message"] = "新 issue 已入 KAM 任务池，但拉起全局无人值守失败。"
                summary["autodriveError"] = f"{type(autodrive_exc).__name__}: {autodrive_exc}"
                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 1

            write_json(summary_path, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        summary["status"] = "failed"
        summary["message"] = f"{type(exc).__name__}: {exc}"
        write_json(summary_path, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
