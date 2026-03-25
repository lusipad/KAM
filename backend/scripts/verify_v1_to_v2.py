from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.conversation import Message, Run, Thread, ThreadRunArtifact
from app.models.project import Project, ProjectResource
from scripts.legacy_schema import LEGACY_TABLE_NAMES, build_legacy_metadata
from scripts.migrate_v1_to_v2 import create_engine_for_url, stable_uuid


def verify(database_url: str) -> dict[str, Any]:
    engine = create_engine_for_url(database_url)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    metadata = build_legacy_metadata()
    legacy_present = [name for name in LEGACY_TABLE_NAMES if name in existing_tables]
    metadata.reflect(bind=engine, only=legacy_present, extend_existing=True)
    tables = metadata.tables

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    errors: list[str] = []
    try:
        task_rows = session.execute(select(tables['task_cards'])).mappings().all() if 'task_cards' in tables else []
        ref_rows = session.execute(select(tables['task_refs'])).mappings().all() if 'task_refs' in tables else []
        snapshot_rows = session.execute(select(tables['context_snapshots'])).mappings().all() if 'context_snapshots' in tables else []
        run_rows = session.execute(select(tables['agent_runs'])).mappings().all() if 'agent_runs' in tables else []
        artifact_rows = session.execute(select(tables['run_artifacts'])).mappings().all() if 'run_artifacts' in tables else []
        autonomy_session_rows = session.execute(select(tables['autonomy_sessions'])).mappings().all() if 'autonomy_sessions' in tables else []
        autonomy_cycle_rows = session.execute(select(tables['autonomy_cycles'])).mappings().all() if 'autonomy_cycles' in tables else []

        for row in task_rows:
            task_id = str(row['id'])
            if session.get(Project, task_id) is None:
                errors.append(f'缺少项目映射: task_cards.{task_id}')
            if session.get(Thread, stable_uuid('legacy-thread', task_id)) is None:
                errors.append(f'缺少默认线程映射: task_cards.{task_id}')

        for row in ref_rows:
            if session.get(ProjectResource, str(row['id'])) is None:
                errors.append(f'缺少资源映射: task_refs.{row["id"]}')

        for row in snapshot_rows:
            if session.get(Message, stable_uuid('legacy-snapshot-message', str(row['id']))) is None:
                errors.append(f'缺少快照消息映射: context_snapshots.{row["id"]}')

        for row in run_rows:
            run_id = str(row['id'])
            if session.get(Run, run_id) is None:
                errors.append(f'缺少 Run 映射: agent_runs.{run_id}')
            if session.get(Message, stable_uuid('legacy-run-message', run_id)) is None:
                errors.append(f'缺少 Run 消息映射: agent_runs.{run_id}')

        for row in artifact_rows:
            if session.get(ThreadRunArtifact, str(row['id'])) is None:
                errors.append(f'缺少 artifact 映射: run_artifacts.{row["id"]}')

        for row in autonomy_session_rows:
            if session.get(Message, stable_uuid('legacy-autonomy-session-message', str(row['id']))) is None:
                errors.append(f'缺少自治会话映射: autonomy_sessions.{row["id"]}')

        for row in autonomy_cycle_rows:
            artifact_id = stable_uuid('legacy-autonomy-cycle-artifact', str(row['id']))
            if session.get(ThreadRunArtifact, artifact_id) is None:
                errors.append(f'缺少自治循环映射: autonomy_cycles.{row["id"]}')

        summary = {
            'databaseUrl': database_url,
            'legacyCounts': {
                'task_cards': len(task_rows),
                'task_refs': len(ref_rows),
                'context_snapshots': len(snapshot_rows),
                'agent_runs': len(run_rows),
                'run_artifacts': len(artifact_rows),
                'autonomy_sessions': len(autonomy_session_rows),
                'autonomy_cycles': len(autonomy_cycle_rows),
            },
            'v2Counts': {
                'projects': session.query(Project).count(),
                'project_resources': session.query(ProjectResource).count(),
                'threads': session.query(Thread).count(),
                'messages': session.query(Message).count(),
                'runs': session.query(Run).count(),
                'thread_run_artifacts': session.query(ThreadRunArtifact).count(),
            },
            'errors': errors,
            'ok': not errors,
        }
        return summary
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description='Verify KAM v1 -> v2 migration integrity.')
    parser.add_argument('--database-url', default=settings.DATABASE_URL)
    args = parser.parse_args()
    report = verify(args.database_url)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(0 if report['ok'] else 1)


if __name__ == '__main__':
    main()
