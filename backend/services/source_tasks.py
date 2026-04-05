from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from config import settings
from models import now


GITHUB_PR_REVIEW_SOURCE_KIND = "github_pr_review_comments"

_SOURCE_TASK_LOCK_DIRNAME = "source-task-locks"
_SOURCE_TASK_LOCK_TTL_SECONDS = 15.0
_SOURCE_TASK_LOCK_WAIT_SECONDS = 10.0
_SOURCE_TASK_LOCK_POLL_SECONDS = 0.02


def source_dedup_key(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    value = metadata.get("sourceDedupKey")
    return value.strip() if isinstance(value, str) and value.strip() else None


def merge_source_task_metadata(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged.update(incoming)
    source_kind = str(merged.get("sourceKind") or "").strip()
    if source_kind == GITHUB_PR_REVIEW_SOURCE_KIND:
        merged_comments = merge_github_review_comments(
            existing.get("sourceReviewComments"),
            incoming.get("sourceReviewComments"),
        )
        merged["sourceReviewComments"] = merged_comments
        repo = str(merged.get("sourceRepo") or "").strip()
        pull_number = _normalize_pull_number(merged.get("sourcePullNumber"))
        if repo and pull_number is not None and merged_comments:
            merged["recommendedPrompt"] = build_github_review_task_prompt(repo, pull_number, merged_comments)
    return merged


def merge_github_review_comments(
    existing_comments: Any,
    incoming_comments: Any,
) -> list[dict[str, Any]]:
    merged_by_key: dict[str, dict[str, Any]] = {}
    ordered_keys: list[str] = []
    for raw in [*(existing_comments or []), *(incoming_comments or [])]:
        if not isinstance(raw, dict):
            continue
        key = _github_review_comment_key(raw)
        if key not in ordered_keys:
            ordered_keys.append(key)
        merged_by_key[key] = dict(raw)
    return [merged_by_key[key] for key in ordered_keys if key in merged_by_key]


def build_github_review_task_title(repo: str, pull_number: int) -> str:
    return f"处理 {repo} PR #{pull_number} 新发现的评审评论"


def build_github_review_task_description(
    repo: str,
    pull_number: int,
    review_comments: list[dict[str, Any]],
) -> str:
    summarized_comments = _summarize_github_review_comments(review_comments, limit=3)
    description_lines = [
        f"把 {repo} PR #{pull_number} 新增或更新的 review comments 接入 KAM 任务池，并在对应分支上修复、验证、回推。",
    ]
    if summarized_comments:
        description_lines.append("待处理评论摘要：")
        description_lines.extend(f"- {line}" for line in summarized_comments)
    return "\n".join(description_lines)


def build_github_review_task_prompt(
    repo: str,
    pull_number: int,
    review_comments: list[dict[str, Any]],
) -> str:
    scope = f"{repo} PR #{pull_number}"
    pending_comments = [
        {
            "id": item.get("id"),
            "path": item.get("path"),
            "line": item.get("line"),
            "user": item.get("user"),
            "url": item.get("html_url") or item.get("url"),
            "body": " ".join(str(item.get("body", "")).split())[:180],
        }
        for item in review_comments
        if isinstance(item, dict)
    ]
    return (
        f"处理 {scope} 新发现的评审评论：能自动修复的直接修复并验证，"
        "需要额外产品、架构或业务上下文的评论则整理成简洁回复草稿。"
        f" 当前待处理的评论是：{json.dumps(pending_comments, ensure_ascii=False)}。"
        " 先确认当前工作目录对应这条 PR 的代码；如果不是，用 GitHub PR ref 抓取对应分支。"
        " 只直接修复能在当前上下文里明确落地的问题，并运行与改动相关的最小验证。"
        " 需要产品、架构或需求澄清的评论不要猜，明确写出阻塞点和建议回复。"
    )


def build_github_review_task_description_from_metadata(metadata: dict[str, Any]) -> str | None:
    if str(metadata.get("sourceKind") or "").strip() != GITHUB_PR_REVIEW_SOURCE_KIND:
        return None
    repo = str(metadata.get("sourceRepo") or "").strip()
    pull_number = _normalize_pull_number(metadata.get("sourcePullNumber"))
    source_review_comments = metadata.get("sourceReviewComments")
    if not repo or pull_number is None or not isinstance(source_review_comments, list) or not source_review_comments:
        return None
    comments = [dict(item) for item in source_review_comments if isinstance(item, dict)]
    if not comments:
        return None
    return build_github_review_task_description(repo, pull_number, comments)


@asynccontextmanager
async def source_task_guard(dedup_key: str | None):
    owner_id: str | None = None
    if dedup_key:
        owner_id = await _acquire_source_task_lock(dedup_key)
    try:
        yield
    finally:
        if dedup_key and owner_id is not None:
            await asyncio.to_thread(_release_source_task_lock, dedup_key, owner_id)


async def _acquire_source_task_lock(dedup_key: str) -> str:
    deadline = asyncio.get_running_loop().time() + _SOURCE_TASK_LOCK_WAIT_SECONDS
    while True:
        owner_id = await asyncio.to_thread(_try_acquire_source_task_lock, dedup_key)
        if owner_id is not None:
            return owner_id
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"timed out waiting for source task lock: {dedup_key}")
        await asyncio.sleep(_SOURCE_TASK_LOCK_POLL_SECONDS)


def _try_acquire_source_task_lock(dedup_key: str) -> str | None:
    lock_path = _source_task_lock_path(dedup_key)
    existing = _load_source_task_lock_payload(lock_path)
    if existing is not None and not _is_source_task_lock_stale(existing):
        return None
    if existing is not None:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            latest = _load_source_task_lock_payload(lock_path)
            if latest is not None and not _is_source_task_lock_stale(latest):
                return None

    owner_id = uuid.uuid4().hex
    payload = {
        "ownerId": owner_id,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "dedupKey": dedup_key,
        "acquiredAt": now().isoformat(),
    }
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return None
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except Exception:
        lock_path.unlink(missing_ok=True)
        raise
    return owner_id


def _release_source_task_lock(dedup_key: str, owner_id: str) -> None:
    lock_path = _source_task_lock_path(dedup_key)
    existing = _load_source_task_lock_payload(lock_path)
    if existing is None or existing.get("ownerId") != owner_id:
        return
    lock_path.unlink(missing_ok=True)


def _source_task_lock_path(dedup_key: str) -> Path:
    digest = hashlib.sha256(dedup_key.encode("utf-8")).hexdigest()
    return settings.storage_dir / _SOURCE_TASK_LOCK_DIRNAME / f"{digest}.json"


def _load_source_task_lock_payload(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def _is_source_task_lock_stale(payload: dict[str, Any]) -> bool:
    acquired_at = payload.get("acquiredAt")
    if not isinstance(acquired_at, str) or not acquired_at.strip():
        return True
    try:
        acquired_at_value = datetime.fromisoformat(acquired_at)
    except ValueError:
        return True
    return now() - acquired_at_value > timedelta(seconds=_SOURCE_TASK_LOCK_TTL_SECONDS)


def _normalize_pull_number(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _github_review_comment_key(comment: dict[str, Any]) -> str:
    comment_id = comment.get("id")
    if isinstance(comment_id, int):
        return f"id:{comment_id}"
    if isinstance(comment_id, str) and comment_id.strip():
        return f"id:{comment_id.strip()}"
    comment_url = comment.get("html_url")
    if isinstance(comment_url, str) and comment_url.strip():
        return f"url:{comment_url.strip()}"
    path = str(comment.get("path", "")).strip()
    line = comment.get("line")
    body = " ".join(str(comment.get("body", "")).split())
    return f"fallback:{path}:{line}:{body}"


def _summarize_github_review_comments(
    review_comments: list[dict[str, Any]],
    *,
    limit: int,
) -> list[str]:
    summaries: list[str] = []
    for item in review_comments[:limit]:
        body = " ".join(str(item.get("body", "")).split())
        path = str(item.get("path", "")).strip()
        line = item.get("line")
        location = f"{path}:{line}" if path and line else path
        summary = f"{location} · {body[:160]}".strip(" ·")
        if summary:
            summaries.append(summary)
    return summaries
