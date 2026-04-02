from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import RunArtifact


class ArtifactStore:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_run(self, run_id: str) -> list[RunArtifact]:
        result = await self.db.execute(
            select(RunArtifact).where(RunArtifact.run_id == run_id).order_by(RunArtifact.created_at.asc())
        )
        return list(result.scalars())

    async def replace_for_run(
        self,
        run_id: str,
        artifacts: Iterable[dict[str, Any]],
    ) -> list[RunArtifact]:
        await self.db.execute(delete(RunArtifact).where(RunArtifact.run_id == run_id))
        created: list[RunArtifact] = []
        for artifact in artifacts:
            record = RunArtifact(
                run_id=run_id,
                type=str(artifact["type"]),
                content=str(artifact.get("content") or ""),
                metadata_=artifact.get("metadata"),
            )
            self.db.add(record)
            created.append(record)
        return created
