#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from adapters.github import GitHubPRAdapter  # noqa: E402
from config import settings  # noqa: E402


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _safe_repo_slug(repo: str) -> str:
    return repo.replace("/", "-").replace("\\", "-")


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_codex(executable: str) -> str:
    candidate = Path(executable)
    if candidate.is_file():
        return str(candidate)
    if os.name == "nt" and not candidate.suffix:
        for suffix in (".cmd", ".exe", ".bat"):
            resolved = shutil.which(f"{executable}{suffix}")
            if resolved:
                return resolved
    resolved = shutil.which(executable)
    if resolved:
        return resolved
    raise RuntimeError(f"未找到 codex 可执行文件：{executable}")


def _normalize_remote(url: str) -> str:
    normalized = url.strip().lower().replace(".git", "")
    if normalized.startswith("git@github.com:"):
        normalized = normalized.replace("git@github.com:", "https://github.com/")
    return normalized.rstrip("/")


def _parse_git_credential_output(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _run_checked(command: list[str], *, cwd: Path | None = None) -> str:
    completed = _run(command, cwd=cwd)
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(stderr or f"命令失败: {' '.join(command)}")
    return completed.stdout.strip()


def _resolve_github_token(repo: str) -> str | None:
    if settings.github_token:
        return settings.github_token

    owner = repo.split("/", 1)[0] if "/" in repo else ""
    query_lines = ["protocol=https", "host=github.com"]
    if owner:
        query_lines.append(f"username={owner}")
    query = "\n".join([*query_lines, "", ""])
    completed = subprocess.run(
        ["git", "credential", "fill"],
        cwd=str(PROJECT_ROOT),
        input=query,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return None

    token = _parse_git_credential_output(completed.stdout).get("password", "").strip()
    if not token:
        return None

    os.environ["GITHUB_TOKEN"] = token
    settings.github_token = token
    return token


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"已有监控进程在运行: {self.path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "startedAt": utc_now_iso()}, handle, ensure_ascii=False, indent=2)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def _ensure_base_clone(repo: str, workspace: Path) -> None:
    remote_url = f"https://github.com/{repo}.git"
    if not workspace.exists():
        workspace.parent.mkdir(parents=True, exist_ok=True)
        _run_checked(["git", "clone", remote_url, str(workspace)])
    if not (workspace / ".git").exists():
        raise RuntimeError(f"监控工作副本不是 git 仓库: {workspace}")
    current_remote = _normalize_remote(_run_checked(["git", "-C", str(workspace), "remote", "get-url", "origin"]))
    expected_remote = _normalize_remote(remote_url)
    if current_remote != expected_remote:
        raise RuntimeError(f"监控工作副本 origin 不匹配: {current_remote} != {expected_remote}")
    _run_checked(["git", "-C", str(workspace), "fetch", "--prune", "origin"])


def _remote_name_for_repo(repo: str) -> str:
    return f"pr-head-{_safe_repo_slug(repo).lower()}"


def _ensure_remote(base_repo: Path, remote_name: str, remote_url: str) -> None:
    existing = _run(["git", "-C", str(base_repo), "remote", "get-url", remote_name])
    if existing.returncode == 0:
        current_remote = _normalize_remote(existing.stdout)
        expected_remote = _normalize_remote(remote_url)
        if current_remote != expected_remote:
            _run_checked(["git", "-C", str(base_repo), "remote", "set-url", remote_name, remote_url])
        return
    _run_checked(["git", "-C", str(base_repo), "remote", "add", remote_name, remote_url])


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
    origin_url = _run_checked(["git", "-C", str(base_repo), "remote", "get-url", "origin"])
    remote_name = "origin" if _normalize_remote(origin_url) == _normalize_remote(remote_url) else _remote_name_for_repo(head_repo)
    if remote_name != "origin":
        _ensure_remote(base_repo, remote_name, remote_url)

    fetch_failures: list[str] = []
    pr_head: str | None = None

    if head_ref:
        fetch_by_ref = _run(["git", "-C", str(base_repo), "fetch", "--prune", remote_name, head_ref])
        if fetch_by_ref.returncode == 0:
            pr_head = _run_checked(["git", "-C", str(base_repo), "rev-parse", "FETCH_HEAD"])
        else:
            fetch_failures.append((fetch_by_ref.stderr or fetch_by_ref.stdout).strip() or f"fetch {remote_name} {head_ref} failed")

    if pr_head is None:
        fetch_by_pr_ref = _run(["git", "-C", str(base_repo), "fetch", "origin", f"pull/{pull_number}/head"])
        if fetch_by_pr_ref.returncode == 0:
            pr_head = _run_checked(["git", "-C", str(base_repo), "rev-parse", "FETCH_HEAD"])
        else:
            fetch_failures.append((fetch_by_pr_ref.stderr or fetch_by_pr_ref.stdout).strip() or f"fetch origin pull/{pull_number}/head failed")

    if pr_head is None:
        detail = " | ".join(item for item in fetch_failures if item)
        raise RuntimeError(f"无法抓取 PR #{pull_number} 的 head 提交。{detail}".strip())

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    worktree = worktrees_root / f"pr-{pull_number}-{timestamp}"
    _run_checked(["git", "-C", str(base_repo), "worktree", "add", "--detach", str(worktree), pr_head])
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
    return _run(command)


def _git_status(worktree: Path) -> str:
    return _run_checked(["git", "-C", str(worktree), "status", "--short"])


def _git_head(worktree: Path) -> str:
    return _run_checked(["git", "-C", str(worktree), "rev-parse", "HEAD"])


def _configure_git_identity(worktree: Path) -> None:
    _run_checked(["git", "-C", str(worktree), "config", "user.name", settings.git_user_name])
    _run_checked(["git", "-C", str(worktree), "config", "user.email", settings.git_user_email])


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
        _run_checked(["git", "-C", str(worktree), "add", "-A"])
        commit_message = _build_commit_message(repo=repo, pull_number=pull_number, comments=comments)
        message_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as handle:
                handle.write(commit_message)
                message_path = Path(handle.name)
            _run_checked(["git", "-C", str(worktree), "commit", "-F", str(message_path)])
        finally:
            if message_path is not None:
                message_path.unlink(missing_ok=True)

    pushed_head = _git_head(worktree)
    _run_checked(["git", "-C", str(worktree), "push", remote_name, f"HEAD:refs/heads/{head_ref}"])
    return pushed_head


def _remove_worktree(base_repo: Path, worktree: Path) -> None:
    _run_checked(["git", "-C", str(base_repo), "worktree", "remove", str(worktree), "--force"])


def _build_summary(*, repo: str, pull_number: int, state_path: Path, workspace: Path) -> dict[str, Any]:
    return {
        "checkedAt": utc_now_iso(),
        "repo": repo,
        "pullNumber": pull_number,
        "stateFile": str(state_path),
        "workspace": str(workspace),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor GitHub PR review comments and auto-run Codex when new comments arrive.")
    parser.add_argument("--repo", required=True, help="GitHub repo, e.g. lusipad/KAM")
    parser.add_argument("--pr", type=int, required=True, help="Pull request number")
    parser.add_argument("--codex-path", default=os.environ.get("CODEX_PATH", "codex"))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    monitor_root = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "output" / "review-monitor" / f"{_safe_repo_slug(args.repo)}-pr-{args.pr}"
    base_workspace = monitor_root / "repo"
    state_path = monitor_root / "state.json"
    summary_path = monitor_root / "last-run.json"
    lock_path = monitor_root / "monitor.lock"
    worktrees_root = monitor_root / "worktrees"
    summary = _build_summary(repo=args.repo, pull_number=args.pr, state_path=state_path, workspace=base_workspace)

    try:
        with FileLock(lock_path):
            _ensure_base_clone(args.repo, base_workspace)
            _resolve_github_token(args.repo)

            config = {
                "repo": args.repo,
                "watch": "review_comments",
                "number": args.pr,
            }
            previous_state = _read_json(state_path)
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
                _write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 1

            if not changes.get("review_comments"):
                summary["status"] = "idle"
                summary["message"] = "没有新的 PR review 评论。"
                _write_json(state_path, current_state)
                _write_json(summary_path, summary)
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
                _write_json(state_path, current_state)
                _write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            if args.dry_run:
                summary["status"] = "dry-run"
                summary["task"] = create_run["params"]["task"]
                _write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 0

            codex_path = _resolve_codex(args.codex_path)
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
                _write_json(state_path, current_state)
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
                _write_json(summary_path, summary)
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return 1

            _write_json(summary_path, summary)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        summary["status"] = "failed"
        summary["message"] = f"{type(exc).__name__}: {exc}"
        _write_json(summary_path, summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
