from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ReviewCompare, Task, TaskRun


class ReviewCompareService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, task_id: str, run_ids: list[str], *, title: str | None = None) -> ReviewCompare | None:
        task = await self.db.get(Task, task_id)
        if task is None:
            return None

        run_ids = [run_id for run_id in dict.fromkeys(run_ids) if run_id]
        if len(run_ids) < 2:
            raise ValueError("compare_requires_at_least_two_runs")

        result = await self.db.execute(select(TaskRun).where(TaskRun.id.in_(run_ids)))
        runs = list(result.scalars())
        if len(runs) != len(run_ids):
            raise ValueError("compare_contains_missing_runs")

        if any(run.task_id != task.id for run in runs):
            raise ValueError("compare_runs_do_not_belong_to_task")

        compare = ReviewCompare(
            task_id=task.id,
            title=(title or f"{task.title} · compare").strip()[:200],
            run_ids=run_ids,
            summary=self._build_summary(runs),
        )
        self.db.add(compare)
        await self.db.commit()
        await self.db.refresh(compare)
        return compare

    def _build_summary(self, runs: list[TaskRun]) -> str:
        lines = [f"对比 {len(runs)} 个 run："]
        for run in runs:
            file_count = len(run.changed_files or [])
            summary = (run.result_summary or run.task or "").strip()
            if len(summary) > 140:
                summary = f"{summary[:139]}…"
            lines.append(f"- {run.agent} · {run.status} · {file_count} files · {summary}")
        return "\n".join(lines)
