from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Task


DEPENDENCY_METADATA_KEY = "dependsOnTaskIds"
DEPENDENCY_RESOLVED_STATUSES = {"done", "verified"}


@dataclass(frozen=True)
class TaskDependencyRecord:
    task_id: str
    title: str
    status: str
    resolved: bool
    missing: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "taskId": self.task_id,
            "title": self.title,
            "status": self.status,
            "resolved": self.resolved,
            "missing": self.missing,
        }


@dataclass(frozen=True)
class TaskDependencyState:
    depends_on_task_ids: list[str]
    dependencies: list[TaskDependencyRecord]
    blocking_task_ids: list[str]
    blocked_by: list[TaskDependencyRecord]
    ready: bool
    summary: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "dependsOnTaskIds": self.depends_on_task_ids,
            "dependencies": [item.to_dict() for item in self.dependencies],
            "blockingTaskIds": self.blocking_task_ids,
            "blockedBy": [item.to_dict() for item in self.blocked_by],
            "ready": self.ready,
            "summary": self.summary,
        }


def normalize_dependency_task_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate or candidate in normalized:
            continue
        normalized.append(candidate)
    return normalized


def task_dependency_ids(metadata: dict[str, Any] | None) -> list[str]:
    return normalize_dependency_task_ids((metadata or {}).get(DEPENDENCY_METADATA_KEY))


def with_dependency_task_ids(metadata: dict[str, Any] | None, depends_on_task_ids: list[str]) -> dict[str, Any] | None:
    next_metadata = dict(metadata or {})
    normalized = normalize_dependency_task_ids(depends_on_task_ids)
    if normalized:
        next_metadata[DEPENDENCY_METADATA_KEY] = normalized
    else:
        next_metadata.pop(DEPENDENCY_METADATA_KEY, None)
    return next_metadata or None


def dependency_is_resolved(task: Task | None) -> bool:
    if task is None:
        return False
    return task.status in DEPENDENCY_RESOLVED_STATUSES


def build_task_dependency_state(task: Task, tasks_by_id: dict[str, Task]) -> TaskDependencyState:
    depends_on_task_ids = task_dependency_ids(task.metadata_ or {})
    dependencies: list[TaskDependencyRecord] = []
    blocked_by: list[TaskDependencyRecord] = []

    for dependency_task_id in depends_on_task_ids:
        dependency_task = tasks_by_id.get(dependency_task_id)
        if dependency_task is None:
            record = TaskDependencyRecord(
                task_id=dependency_task_id,
                title=f"缺失任务 {dependency_task_id}",
                status="missing",
                resolved=False,
                missing=True,
            )
        else:
            record = TaskDependencyRecord(
                task_id=dependency_task.id,
                title=dependency_task.title,
                status=dependency_task.status,
                resolved=dependency_is_resolved(dependency_task),
            )
        dependencies.append(record)
        if not record.resolved:
            blocked_by.append(record)

    summary = None
    if blocked_by:
        summary = "依赖未完成：" + "、".join(item.title for item in blocked_by[:2])
        if len(blocked_by) > 2:
            summary += f" 等 {len(blocked_by)} 项"
    elif dependencies:
        summary = "依赖已满足，可以继续执行。"

    return TaskDependencyState(
        depends_on_task_ids=depends_on_task_ids,
        dependencies=dependencies,
        blocking_task_ids=[item.task_id for item in blocked_by],
        blocked_by=blocked_by,
        ready=not blocked_by,
        summary=summary,
    )


def task_has_unresolved_dependencies(task: Task, tasks_by_id: dict[str, Task]) -> bool:
    return not build_task_dependency_state(task, tasks_by_id).ready


async def load_tasks_by_id(db: AsyncSession) -> dict[str, Task]:
    result = await db.execute(select(Task))
    return {task.id: task for task in result.scalars()}


def validate_dependency_task_ids(
    *,
    task_id: str | None,
    dependency_task_ids: list[str],
    tasks_by_id: dict[str, Task],
) -> tuple[list[str], str | None]:
    normalized = normalize_dependency_task_ids(dependency_task_ids)
    for dependency_task_id in normalized:
        if task_id is not None and dependency_task_id == task_id:
            return [], "任务不能依赖自己"
        if dependency_task_id not in tasks_by_id:
            return [], f"依赖任务不存在：{dependency_task_id}"
    if task_id is not None and _would_create_cycle(task_id, normalized, tasks_by_id):
        return [], "任务依赖不能形成循环"
    return normalized, None


def _would_create_cycle(task_id: str, dependency_task_ids: list[str], tasks_by_id: dict[str, Task]) -> bool:
    graph = {
        current_task_id: task_dependency_ids(task.metadata_ or {})
        for current_task_id, task in tasks_by_id.items()
    }
    graph[task_id] = dependency_task_ids

    visited: set[str] = set()
    stack = list(dependency_task_ids)
    while stack:
        current = stack.pop()
        if current == task_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(graph.get(current, []))
    return False
