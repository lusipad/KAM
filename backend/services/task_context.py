from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import ContextSnapshot, Task, now


class TaskContextService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build_snapshot(self, task_id: str, *, focus: str | None = None) -> ContextSnapshot | None:
        result = await self.db.execute(
            select(Task)
            .where(Task.id == task_id)
            .options(selectinload(Task.refs))
            .execution_options(populate_existing=True)
        )
        task = result.scalars().first()
        if task is None:
            return None

        lines = ["## Task", f"标题：{task.title}"]
        if task.description:
            lines.append(f"描述：{task.description}")
        if task.repo_path:
            lines.append(f"仓库：{task.repo_path}")
        lines.append(f"状态：{task.status}")
        lines.append(f"优先级：{task.priority}")
        if task.labels:
            lines.append(f"标签：{', '.join(task.labels)}")

        lines.append("")
        lines.append("## Refs")
        if task.refs:
            for ref in task.refs:
                lines.append(f"- [{ref.kind}] {ref.label}: {ref.value}")
        else:
            lines.append("- 暂无引用")

        if focus:
            lines.append("")
            lines.append("## Focus")
            lines.append(focus.strip())

        snapshot = ContextSnapshot(
            task_id=task.id,
            summary=f"{task.title} · {len(task.refs)} refs",
            content="\n".join(lines),
            focus=focus.strip() if focus else None,
        )
        self.db.add(snapshot)
        task.updated_at = now()
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot
