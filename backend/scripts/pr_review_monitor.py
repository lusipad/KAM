#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from adapters.github import GitHubPRAdapter  # noqa: E402
from config import settings  # noqa: E402
from github_monitor_support import (  # noqa: E402
    FileLock,
    build_summary,
    ensure_base_clone,
    enqueue_task_to_harness,
    normalize_remote,
    read_json,
    resolve_codex,
    resolve_github_token,
    run,
    run_checked,
    safe_repo_slug,
    start_harness_global_autodrive,
    write_json,
)
from services.source_tasks import (  # noqa: E402
    GITHUB_PR_REVIEW_SOURCE_KIND,
    build_github_review_task_description,
    build_github_review_task_title,
)


def _remote_name_for_repo(repo: str) -> str:
    return f"pr-head-{safe_repo_slug(repo).lower()}"


def _ensure_remote(base_repo: Path, remote_name: str, remote_url: str) -> None:
    existing = run(["git", "-C", str(base_repo), "remote", "get-url", remote_name])
    if existing.returncode == 0:
        current_remote = normalize_remote(existing.stdout)
        expected_remote = normalize_remote(remote_url)
        if current_remote != expected_remote:
            run_checked(["git", "-C", str(base_repo), "remote", "set-url", remote_name, remote_url])
        return
    run_checked(["git", "-C", str(base_repo), "remote", "add", remote_name, remote_url])


def _prepare_pr_worktree(
    base_repo: Path,
    worktrees_root: Path,
    *,
    repo: str,
    pull_number: int,
    meta: dict[str, Any],
) -> tuple[Path, str, str, str | None, str]:
    worktrees_root.mkdir(parents=True, exist_ok=True)
    head_repo = str(meta.get("headRepo") or repo)
    head_ref = meta.get("headRef")
    remote_url = f"https://github.com/{head_repo}.git"
    origin_url = run_checked(["git", "-C", str(base_repo), "remote", "get-url", "origin"])
    remote_name = "origin" if normalize_remote(origin_url) == normalize_remote(remote_url) else _remote_name_for_repo(head_repo)
    if remote_name != "origin":
        _ensure_remote(base_repo, remote_name, remote_url)

    fetch_failures: list[str] = []
    pr_head: str | None = None

    if head_ref:
        fetch_by_ref = run(["git", "-C", str(base_repo), "fetch", "--prune", remote_name, head_ref])
        if fetch_by_ref.returncode == 0:
            pr_head = run_checked(["git", "-C", str(base_repo), "rev-parse", "FETCH_HEAD"])
        else:
            fetch_failures.append((fetch_by_ref.stderr or fetch_by_ref.stdout).strip() or f"fetch {remote_name} {head_ref} failed")

    if pr_head is None:
        fetch_by_pr_ref = run(["git", "-C", str(base_repo), "fetch", "origin", f"pull/{pull_number}/head"])
        if fetch_by_pr_ref.returncode == 0:
            pr_head = run_checked(["git", "-C", str(base_repo), "rev-parse", "FETCH_HEAD"])
        else:
            fetch_failures.append((fetch_by_pr_ref.stderr or fetch_by_pr_ref.stdout).strip() or f"fetch origin pull/{pull_number}/head failed")

    if pr_head is None:
        detail = " | ".join(item for item in fetch_failures if item)
        raise RuntimeError(f"无法抓取 PR #{pull_number} 的 head 提交。{detail}".strip())

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    worktree = worktrees_root / f"pr-{pull_number}-{timestamp}"
    run_checked(["git", "-C", str(base_repo), "worktree", "add", "--detach", str(worktree), pr_head])
    return worktree, pr_head, remote_name, head_ref, head_repo


def _run_codex(codex_path: str, worktree: Path, task: str) -> subprocess.CompletedProcess[str]:
    command = [
        codex_path,
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        str(worktree),
        task,
    ]
    return run(command)


def _git_status(worktree: Path) -> str:
    return run_checked(["git", "-C", str(worktree), "status", "--short"])


def _git_head(worktree: Path) -> str:
    return run_checked(["git", "-C", str(worktree), "rev-parse", "HEAD"])


def _configure_git_identity(worktree: Path) -> None:
    run_checked(["git", "-C", str(worktree), "config", "user.name", settings.git_user_name])
    run_checked(["git", "-C", str(worktree), "config", "user.email", settings.git_user_email])


def _build_commit_message(*, repo: str, pull_number: int, comments: list[dict[str, Any]]) -> str:
    message_lines = [
        f"Address new review feedback on {repo} PR #{pull_number}",
        "",
        "Apply Codex-generated changes for newly detected review comments in the scheduled PR monitor lane.",
        "",
        "Constraint: Automated monitor should only act on directly actionable review comments",
        "Confidence: medium",
        "Scope-risk: narrow",
        "Reversibility: clean",
        "Directive: Verify reviewer intent before broadening this automation beyond clear code-level fixes",
        "Tested: Codex run completed with repository-local verification",
        "Not-tested: Manual reviewer confirmation on the pushed branch",
    ]
    for item in comments[:3]:
        url = item.get("html_url") or item.get("url")
        if url:
            message_lines.append(f"Related: {url}")
    return "\n".join(message_lines)


def _finalize_and_push(
    *,
    worktree: Path,
    expected_head: str,
    remote_name: str,
    head_ref: str | None,
    repo: str,
    pull_number: int,
    comments: list[dict[str, Any]],
) -> str | None:
    current_head = _git_head(worktree)
    worktree_status = _git_status(worktree)
    if not worktree_status.strip() and current_head == expected_head:
        return None
    if not head_ref:
        raise RuntimeError("PR metadata 缺少 headRef，无法自动推送修复。")

    if worktree_status.strip():
        _configure_git_identity(worktree)
        run_checked(["git", "-C", str(worktree), "add", "-A"])
        commit_message = _build_commit_message(repo=repo, pull_number=pull_number, comments=comments)
        message_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as handle:
                handle.write(commit_message)
                message_path = Path(handle.name)
            run_checked(["git", "-C", str(worktree), "commit", "-F", str(message_path)])
        finally:
            if message_path is not None:
                message_path.unlink(missing_ok=True)

    pushed_head = _git_head(worktree)
    run_checked(["git", "-C", str(worktree), "push", remote_name, f"HEAD:refs/heads/{head_ref}"])
    return pushed_head


def _remove_worktree(base_repo: Path, worktree: Path) -> None:
    run_checked(["git", "-C", str(base_repo), "worktree", "remove", str(worktree), "--force"])


def _build_harness_task_payload(
    *,
    repo: str,
    pull_number: int,
    workspace: Path,
    meta: dict[str, Any],
    changes: dict[str, Any],
    create_run: dict[str, Any],
) -> dict[str, Any]:
    review_comments = list(changes.get("review_comments", []))
    source_kind = GITHUB_PR_REVIEW_SOURCE_KIND
    source_dedup_key = f"{source_kind}:{repo}:{pull_number}"
    title = build_github_review_task_title(repo, pull_number)
    description = build_github_review_task_description(repo, pull_number, review_comments)

    refs: list[dict[str, Any]] = []
    pull_url = meta.get("pullUrl")
    if isinstance(pull_url, str) and pull_url.strip():
        refs.append(
            {
                "kind": "url",
                "label": f"{repo} PR #{pull_number}",
                "value": pull_url.strip(),
                "metadata": {"intakeSourceKind": source_kind},
            }
        )

    unique_paths: list[str] = []
    for item in review_comments:
        path = str(item.get("path", "")).strip()
        if path and path not in unique_paths:
            unique_paths.append(path)
    for path in unique_paths[:5]:
        refs.append(
            {
                "kind": "file",
                "label": f"PR 文件 · {path}",
                "value": path,
                "metadata": {"source": "github_review_comment", "intakeSourceKind": source_kind},
            }
        )

    for item in review_comments[:5]:
        comment_url = item.get("html_url")
        comment_id = item.get("id")
        if isinstance(comment_url, str) and comment_url.strip():
            refs.append(
                {
                    "kind": "url",
                    "label": f"Review comment #{comment_id}",
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
        "sourcePullNumber": pull_number,
        "sourceMeta": meta,
        "sourceReviewComments": review_comments,
    }
    head_repo = meta.get("headRepo")
    head_ref = meta.get("headRef")
    head_sha = meta.get("headSha")
    if isinstance(head_repo, str) and head_repo.strip() and isinstance(head_ref, str) and head_ref.strip():
        metadata["executionRemoteUrl"] = f"https://github.com/{head_repo.strip()}.git"
        metadata["executionRef"] = head_ref.strip()
        metadata["executionPushOnSuccess"] = True
        if isinstance(head_sha, str) and head_sha.strip():
            metadata["executionHeadSha"] = head_sha.strip()

    return {
        "title": title,
        "description": description,
        "repoPath": str(workspace),
        "status": "open",
        "priority": "high",
        "labels": ["dogfood", "github", "pr-review"],
        "metadata": metadata,
        "refs": refs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor GitHub PR review comments and auto-run Codex when new comments arrive.")
    parser.add_argument("--repo", required=True, help="GitHub repo, e.g. lusipad/KAM")
    parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    parser.add_argument("--codex-path", default=os.environ.get("CODEX_PATH", "codex"))
    parser.add_argument("--kam-url", default=os.environ.get("KAM_API_URL", ""))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    monitor_root = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "output" / "review-monitor" / f"{safe_repo_slug(args.repo)}-pr-{args.pr}"
    base_workspace = monitor_root / "repo"
    state_path = monitor_root / "state.json"
    summary_path = monitor_root / "last-run.json"
    lock_path = monitor_root / "monitor.lock"
    worktrees_root = monitor_root / "worktrees"
    summary = build_summary(
        repo=args.repo,
        state_path=state_path,
        workspace=base_workspace,
        extra={"pullNumber": args.pr},
    )

    try:
        with FileLock(lock_path):
            ensure_base_clone(args.repo, base_workspace)
            resolve_github_token(args.repo, project_root=PROJECT_ROOT)

            config = {
                "repo": args.repo,
                "watch": "review_comments",
                "number": args.pr,
            }
            previous_state = read_json(state_path)
            adapter = GitHubPRAdapter()
            current_state = asyncio.run(adapter.fetch(config))
            changes = adapter.diff(previous_state, current_state)

            summary["commentCount"] = len(current_state.get("items", []))
            summary["newCommentCount"] = len(changes.get("review_comments", []))
            summary["meta"] = current_state.get("meta", {})

            current_error = current_state.get("meta", {}).get("error")
            if current_error:
                summary["status"] = "source-error"
                summary["message"] = current_error
                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 1

            if not changes.get("review_comments"):
                summary["status"] = "idle"
                summary["message"] = "没有新的 PR review 评论。"
                write_json(state_path, current_state)
                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            actions = adapter.recommended_actions(
                {"name": f"PR #{args.pr} 评审监控", "config": config},
                changes,
            )
            create_run = next((action for action in actions if action.get("kind") == "create_run"), None)
            if create_run is None:
                summary["status"] = "noop"
                summary["message"] = "检测到新评论，但没有可执行的自动动作。"
                write_json(state_path, current_state)
                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            if args.dry_run:
                summary["status"] = "dry-run"
                summary["task"] = create_run["params"]["task"]
                if args.kam_url:
                    summary["taskMode"] = "harness_queue"
                    summary["enqueuePayload"] = _build_harness_task_payload(
                        repo=args.repo,
                        pull_number=args.pr,
                        workspace=base_workspace,
                        meta=current_state.get("meta", {}),
                        changes=changes,
                        create_run=create_run,
                    )
                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            if args.kam_url:
                task_payload = _build_harness_task_payload(
                    repo=args.repo,
                    pull_number=args.pr,
                    workspace=base_workspace,
                    meta=current_state.get("meta", {}),
                    changes=changes,
                    create_run=create_run,
                )
                created_task = enqueue_task_to_harness(args.kam_url, task_payload)
                summary["taskMode"] = "harness_queue"
                summary["task"] = create_run["params"]["task"]
                summary["taskId"] = created_task.get("id")
                summary["status"] = "enqueued"
                summary["message"] = "检测到新评论，已同步到 KAM 任务池。"
                write_json(state_path, current_state)
                try:
                    summary["autodrive"] = start_harness_global_autodrive(args.kam_url)
                except Exception as autodrive_exc:
                    summary["status"] = "enqueued-with-autodrive-error"
                    summary["message"] = "新评论已入 KAM 任务池，但拉起全局无人值守失败。"
                    summary["autodriveError"] = f"{type(autodrive_exc).__name__}: {autodrive_exc}"
                    write_json(summary_path, summary)
                    print(json.dumps(summary, ensure_ascii=False, indent=2))
                    return 1

                write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            codex_path = resolve_codex(args.codex_path)
            worktree, pr_head, push_remote, head_ref, head_repo = _prepare_pr_worktree(
                base_workspace,
                worktrees_root,
                repo=args.repo,
                pull_number=args.pr,
                meta=current_state.get("meta", {}),
            )
            summary["worktree"] = str(worktree)
            summary["prHead"] = pr_head
            summary["pushRemote"] = push_remote
            summary["headRef"] = head_ref
            summary["headRepo"] = head_repo
            summary["task"] = create_run["params"]["task"]

            completed = _run_codex(codex_path, worktree, create_run["params"]["task"])
            summary["codexExitCode"] = completed.returncode
            summary["codexOutputTail"] = "\n".join((completed.stdout or "").splitlines()[-40:])

            head_after = _git_head(worktree)
            worktree_status = _git_status(worktree)
            summary["worktreeHead"] = head_after
            summary["worktreeDirty"] = bool(worktree_status.strip())
            summary["worktreeStatus"] = worktree_status
            summary["status"] = "run-finished" if completed.returncode == 0 else "run-failed"

            if completed.returncode == 0:
                pushed_head = _finalize_and_push(
                    worktree=worktree,
                    expected_head=pr_head,
                    remote_name=push_remote,
                    head_ref=head_ref,
                    repo=args.repo,
                    pull_number=args.pr,
                    comments=changes.get("review_comments", []),
                )
                write_json(state_path, current_state)
                if pushed_head is None:
                    summary["message"] = "Codex 执行完成，但没有产生代码改动。"
                else:
                    summary["pushedCommit"] = pushed_head
                    summary["status"] = "pushed"
                    summary["message"] = f"检测到新评论，已自动修复并推送到 {head_repo}:{head_ref}。"
                    summary["worktreeDirty"] = False
                    summary["worktreeStatus"] = ""
                try:
                    _remove_worktree(base_workspace, worktree)
                    summary["worktree"] = None
                except Exception as cleanup_exc:
                    summary["cleanupError"] = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
            else:
                summary["message"] = "检测到新评论，但 Codex 自动修复执行失败，保留 worktree 以便重试或人工检查。"
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
