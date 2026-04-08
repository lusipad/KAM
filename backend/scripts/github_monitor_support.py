from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from config import settings


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def safe_repo_slug(repo: str) -> str:
    return repo.replace("/", "-").replace("\\", "-")


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_remote(url: str) -> str:
    normalized = url.strip().lower().replace(".git", "")
    if normalized.startswith("git@github.com:"):
        normalized = normalized.replace("git@github.com:", "https://github.com/")
    return normalized.rstrip("/")


def parse_git_credential_output(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def run_checked(command: list[str], *, cwd: Path | None = None) -> str:
    completed = run(command, cwd=cwd)
    if completed.returncode != 0:
        stderr = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(stderr or f"命令失败: {' '.join(command)}")
    return completed.stdout.strip()


def resolve_github_token(repo: str, *, project_root: Path) -> str | None:
    if settings.github_token:
        return settings.github_token

    owner = repo.split("/", 1)[0] if "/" in repo else ""
    query_lines = ["protocol=https", "host=github.com"]
    if owner:
        query_lines.append(f"username={owner}")
    query = "\n".join([*query_lines, "", ""])
    completed = subprocess.run(
        ["git", "credential", "fill"],
        cwd=str(project_root),
        input=query,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return None

    token = parse_git_credential_output(completed.stdout).get("password", "").strip()
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
            json.dump(
                {"pid": os.getpid(), "hostname": socket.gethostname(), "startedAt": utc_now_iso()},
                handle,
                ensure_ascii=False,
                indent=2,
            )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def ensure_base_clone(repo: str, workspace: Path) -> None:
    remote_url = f"https://github.com/{repo}.git"
    if not workspace.exists():
        workspace.parent.mkdir(parents=True, exist_ok=True)
        run_checked(["git", "clone", remote_url, str(workspace)])
    if not (workspace / ".git").exists():
        raise RuntimeError(f"监控工作副本不是 git 仓库: {workspace}")
    current_remote = normalize_remote(run_checked(["git", "-C", str(workspace), "remote", "get-url", "origin"]))
    expected_remote = normalize_remote(remote_url)
    if current_remote != expected_remote:
        raise RuntimeError(f"监控工作副本 origin 不匹配: {current_remote} != {expected_remote}")
    run_checked(["git", "-C", str(workspace), "fetch", "--prune", "origin"])


def ensure_repo_workspace(repo: str, output_workspace: Path, repo_path: str | None) -> Path:
    if repo_path and repo_path.strip():
        workspace = Path(repo_path).expanduser().resolve()
        if not (workspace / ".git").exists():
            raise RuntimeError(f"repoPath 不是 git 仓库: {workspace}")
        current_remote = normalize_remote(run_checked(["git", "-C", str(workspace), "remote", "get-url", "origin"]))
        expected_remote = normalize_remote(f"https://github.com/{repo}.git")
        if current_remote != expected_remote:
            raise RuntimeError(f"repoPath origin 不匹配: {current_remote} != {expected_remote}")
        run_checked(["git", "-C", str(workspace), "fetch", "--prune", "origin"])
        return workspace

    ensure_base_clone(repo, output_workspace)
    return output_workspace


def resolve_codex(executable: str) -> str:
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


def build_summary(*, repo: str, state_path: Path, workspace: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "checkedAt": utc_now_iso(),
        "repo": repo,
        "stateFile": str(state_path),
        "workspace": str(workspace),
    }
    if extra:
        payload.update(extra)
    return payload


def normalize_api_url(url: str) -> str:
    return url.rstrip("/")


def enqueue_task_to_harness(kam_api_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(f"{normalize_api_url(kam_api_url)}/tasks", json=payload, timeout=30.0)
    response.raise_for_status()
    return response.json()


def start_harness_global_autodrive(kam_api_url: str) -> dict[str, Any]:
    response = httpx.post(f"{normalize_api_url(kam_api_url)}/tasks/autodrive/global/start", timeout=30.0)
    response.raise_for_status()
    return response.json()
