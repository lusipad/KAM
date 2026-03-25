from __future__ import annotations

import argparse
import json
import shutil
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, delete, inspect, select
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.base import Base
from app.models.conversation import Message, Run, Thread, ThreadRunArtifact
from app.models.project import Project, ProjectResource
from scripts.legacy_schema import LEGACY_TABLE_NAMES, build_legacy_metadata

LEGACY_NAMESPACE = uuid.UUID('0c9b5d9d-d0d6-4b68-8f80-b842089f6d72')


def create_engine_for_url(database_url: str):
    kwargs: dict[str, Any] = {'pool_pre_ping': True, 'pool_recycle': 300}
    if database_url.startswith('sqlite'):
        kwargs['connect_args'] = {'check_same_thread': False}
    return create_engine(database_url, **kwargs)


def stable_uuid(prefix: str, value: str) -> str:
    return str(uuid.uuid5(LEGACY_NAMESPACE, f'{prefix}:{value}'))


def to_datetime(value):
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def ensure_json(value, fallback):
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return fallback


def map_project_status(status: str | None) -> str:
    value = (status or '').lower()
    if value in {'done', 'completed', 'archived'}:
        return 'done'
    if value in {'paused', 'blocked', 'on-hold'}:
        return 'paused'
    return 'active'


def map_run_status(status: str | None) -> str:
    value = (status or '').lower()
    if value in {'planned', 'queued'}:
        return 'pending'
    if value == 'running':
        return 'running'
    if value in {'completed', 'passed', 'succeeded', 'success'}:
        return 'passed'
    if value in {'cancelled', 'canceled', 'interrupted'}:
        return 'cancelled'
    if value == 'checking':
        return 'checking'
    return 'failed' if value else 'pending'


def build_backup_path(database_url: str, explicit: str | None = None) -> Path | None:
    if explicit:
        return Path(explicit)
    if not database_url.startswith('sqlite:///'):
        return None
    db_file = Path(database_url.replace('sqlite:///', '', 1))
    if not db_file.exists():
        return None
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    return db_file.with_suffix(db_file.suffix + f'.phase1-backup-{timestamp}')


def backup_sqlite_database(database_url: str, backup_path: str | None = None) -> str | None:
    target = build_backup_path(database_url, backup_path)
    if target is None:
        return None
    source = Path(database_url.replace('sqlite:///', '', 1))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return str(target)


def build_report() -> dict[str, Any]:
    return {
        'legacyCounts': defaultdict(int),
        'created': defaultdict(int),
        'skipped': defaultdict(int),
        'warnings': [],
        'backupPath': None,
        'databaseUrl': None,
        'dryRun': True,
    }


def migrate(database_url: str, dry_run: bool = True, backup_path: str | None = None) -> dict[str, Any]:
    engine = create_engine_for_url(database_url)
    report = build_report()
    report['databaseUrl'] = database_url
    report['dryRun'] = dry_run

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    legacy_present = [name for name in LEGACY_TABLE_NAMES if name in existing_tables]
    if not legacy_present:
        report['warnings'].append('未发现 v1 旧表，无需迁移。')
        return report

    if not dry_run and database_url.startswith('sqlite:///'):
        report['backupPath'] = backup_sqlite_database(database_url, backup_path)

    Base.metadata.create_all(bind=engine)

    metadata = build_legacy_metadata()
    metadata.reflect(bind=engine, only=legacy_present, extend_existing=True)
    tables = metadata.tables

    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        task_rows = session.execute(select(tables['task_cards'])).mappings().all()
        ref_rows = session.execute(select(tables['task_refs'])).mappings().all() if 'task_refs' in tables else []
        snapshot_rows = session.execute(select(tables['context_snapshots'])).mappings().all() if 'context_snapshots' in tables else []
        run_rows = session.execute(select(tables['agent_runs'])).mappings().all() if 'agent_runs' in tables else []
        artifact_rows = session.execute(select(tables['run_artifacts'])).mappings().all() if 'run_artifacts' in tables else []
        autonomy_session_rows = session.execute(select(tables['autonomy_sessions'])).mappings().all() if 'autonomy_sessions' in tables else []
        autonomy_cycle_rows = session.execute(select(tables['autonomy_cycles'])).mappings().all() if 'autonomy_cycles' in tables else []

        report['legacyCounts'].update({
            'task_cards': len(task_rows),
            'task_refs': len(ref_rows),
            'context_snapshots': len(snapshot_rows),
            'agent_runs': len(run_rows),
            'run_artifacts': len(artifact_rows),
            'autonomy_sessions': len(autonomy_session_rows),
            'autonomy_cycles': len(autonomy_cycle_rows),
        })

        refs_by_task = defaultdict(list)
        for row in ref_rows:
            refs_by_task[str(row['task_id'])].append(row)

        sessions_by_task = defaultdict(list)
        for row in autonomy_session_rows:
            sessions_by_task[str(row['task_id'])].append(row)

        cycles_by_session = defaultdict(list)
        for row in autonomy_cycle_rows:
            cycles_by_session[str(row['session_id'])].append(row)

        thread_ids_by_task: dict[str, str] = {}

        for row in task_rows:
            task_id = str(row['id'])
            metadata_payload = ensure_json(row.get('metadata'), {})
            tags = ensure_json(row.get('tags'), [])
            repo_path = metadata_payload.get('repoPath') or metadata_payload.get('repo_path')
            if not repo_path:
                for ref in refs_by_task.get(task_id, []):
                    if str(ref.get('ref_type') or '') in {'repo-path', 'path', 'workspace'}:
                        repo_path = ref.get('value')
                        break
            check_commands = metadata_payload.get('checkCommands') or metadata_payload.get('check_commands') or []
            if not check_commands and sessions_by_task.get(task_id):
                check_commands = ensure_json(sessions_by_task[task_id][0].get('check_commands'), [])

            project = session.get(Project, task_id)
            if project is None:
                report['created']['projects'] += 1
                if not dry_run:
                    project = Project(
                        id=task_id,
                        title=row['title'],
                        status=map_project_status(row.get('status')),
                        repo_path=repo_path,
                        description=row.get('description') or '',
                        check_commands=check_commands,
                        settings_={
                            'legacy': {
                                'source': 'task_card',
                                'priority': row.get('priority'),
                                'tags': tags,
                                'status': row.get('status'),
                                'metadata': metadata_payload,
                            }
                        },
                        created_at=to_datetime(row.get('created_at')),
                        updated_at=to_datetime(row.get('updated_at')) or to_datetime(row.get('created_at')),
                    )
                    session.add(project)
            else:
                report['skipped']['projects'] += 1

            thread_id = stable_uuid('legacy-thread', task_id)
            thread_ids_by_task[task_id] = thread_id
            thread = session.get(Thread, thread_id)
            if thread is None:
                report['created']['threads'] += 1
                if not dry_run:
                    thread = Thread(
                        id=thread_id,
                        project_id=task_id,
                        title=f"{row['title']} · migrated thread",
                        status='completed' if map_project_status(row.get('status')) == 'done' else 'active',
                        created_at=to_datetime(row.get('created_at')),
                        updated_at=to_datetime(row.get('updated_at')) or to_datetime(row.get('created_at')),
                    )
                    session.add(thread)
            else:
                report['skipped']['threads'] += 1

        for row in ref_rows:
            ref_id = str(row['id'])
            resource = session.get(ProjectResource, ref_id)
            if resource is None:
                report['created']['project_resources'] += 1
                if not dry_run:
                    session.add(ProjectResource(
                        id=ref_id,
                        project_id=str(row['task_id']),
                        resource_type=row.get('ref_type') or 'note',
                        title=row.get('label'),
                        uri=row.get('value') or '',
                        pinned=bool(ensure_json(row.get('metadata'), {}).get('pinned', False)),
                        metadata_={
                            'legacy': {
                                'source': 'task_ref',
                                'metadata': ensure_json(row.get('metadata'), {}),
                            }
                        },
                        created_at=to_datetime(row.get('created_at')),
                    ))
            else:
                report['skipped']['project_resources'] += 1

        for row in snapshot_rows:
            task_id = str(row['task_id'])
            message_id = stable_uuid('legacy-snapshot-message', str(row['id']))
            message = session.get(Message, message_id)
            if message is None:
                report['created']['messages'] += 1
                if not dry_run:
                    session.add(Message(
                        id=message_id,
                        thread_id=thread_ids_by_task[task_id],
                        role='system',
                        content=f"导入旧 ContextSnapshot：{row.get('summary') or '无摘要'}",
                        metadata_={
                            'eventType': 'legacy-context-snapshot',
                            'legacySnapshotId': str(row['id']),
                            'snapshotData': ensure_json(row.get('data'), {}),
                        },
                        created_at=to_datetime(row.get('created_at')),
                    ))
            else:
                report['skipped']['messages'] += 1

        run_rows_by_id = {str(row['id']): row for row in run_rows}
        known_run_ids = {str(item.id) for item in session.query(Run.id).all()}
        for row in run_rows:
            run_id = str(row['id'])
            task_id = str(row['task_id'])
            message_id = stable_uuid('legacy-run-message', run_id)
            if session.get(Message, message_id) is None:
                report['created']['messages'] += 1
                if not dry_run:
                    session.add(Message(
                        id=message_id,
                        thread_id=thread_ids_by_task[task_id],
                        role='system',
                        content=f"导入旧 AgentRun：{row.get('agent_name') or row.get('agent_type') or 'agent'}",
                        metadata_={
                            'eventType': 'legacy-run-import',
                            'legacyRunId': run_id,
                            'status': map_run_status(row.get('status')),
                            'agent': row.get('agent_type') or 'custom',
                        },
                        created_at=to_datetime(row.get('created_at')),
                    ))
            else:
                report['skipped']['messages'] += 1

            legacy_metadata = ensure_json(row.get('metadata'), {})
            started_at = to_datetime(row.get('started_at'))
            completed_at = to_datetime(row.get('completed_at'))
            duration_ms = None
            if started_at and completed_at:
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            round_number = int(legacy_metadata.get('round') or 1)
            max_rounds = int(legacy_metadata.get('maxRounds') or legacy_metadata.get('max_rounds') or 1)

            existing_run = session.get(Run, run_id)
            if existing_run is None:
                report['created']['runs'] += 1
                known_run_ids.add(run_id)
                if not dry_run:
                    session.add(Run(
                        id=run_id,
                        thread_id=thread_ids_by_task[task_id],
                        message_id=message_id,
                        agent=row.get('agent_type') or 'custom',
                        model=legacy_metadata.get('model'),
                        reasoning_effort=legacy_metadata.get('reasoningEffort') or legacy_metadata.get('reasoning_effort'),
                        command=row.get('command'),
                        status=map_run_status(row.get('status')),
                        work_dir=row.get('workdir'),
                        round=round_number,
                        max_rounds=max_rounds,
                        duration_ms=duration_ms,
                        error=row.get('error_message'),
                        metadata_={
                            'legacy': {
                                'source': 'agent_run',
                                'agentName': row.get('agent_name'),
                                'status': row.get('status'),
                                'metadata': legacy_metadata,
                                'startedAt': started_at.isoformat() if started_at else None,
                            }
                        },
                        created_at=to_datetime(row.get('created_at')),
                        completed_at=completed_at,
                    ))
            else:
                report['skipped']['runs'] += 1

            if session.get(ThreadRunArtifact, stable_uuid('legacy-run-prompt-artifact', run_id)) is None:
                report['created']['thread_run_artifacts'] += 1
                if not dry_run and (row.get('prompt') or ''):
                    session.add(ThreadRunArtifact(
                        id=stable_uuid('legacy-run-prompt-artifact', run_id),
                        run_id=run_id,
                        artifact_type='prompt',
                        title='legacy imported prompt',
                        content=row.get('prompt') or '',
                        path=None,
                        round=round_number,
                        metadata_={'legacy': {'source': 'agent_run.prompt'}},
                        created_at=to_datetime(row.get('created_at')),
                    ))
            else:
                report['skipped']['thread_run_artifacts'] += 1

        for row in artifact_rows:
            artifact_id = str(row['id'])
            existing = session.get(ThreadRunArtifact, artifact_id)
            run_id = str(row['run_id'])
            run_row = run_rows_by_id.get(run_id, {})
            round_number = int(ensure_json(row.get('metadata'), {}).get('round') or ensure_json(run_row.get('metadata'), {}).get('round') or 1)
            if existing is None:
                report['created']['thread_run_artifacts'] += 1
                if not dry_run:
                    session.add(ThreadRunArtifact(
                        id=artifact_id,
                        run_id=run_id,
                        artifact_type=row.get('artifact_type') or 'legacy',
                        title=row.get('title') or 'legacy artifact',
                        content=row.get('content') or '',
                        path=row.get('path'),
                        round=round_number,
                        metadata_={'legacy': {'source': 'run_artifact', 'metadata': ensure_json(row.get('metadata'), {})}},
                        created_at=to_datetime(row.get('created_at')),
                    ))
            else:
                report['skipped']['thread_run_artifacts'] += 1

        for row in autonomy_session_rows:
            task_id = str(row['task_id'])
            message_id = stable_uuid('legacy-autonomy-session-message', str(row['id']))
            if session.get(Message, message_id) is None:
                report['created']['messages'] += 1
                if not dry_run:
                    session.add(Message(
                        id=message_id,
                        thread_id=thread_ids_by_task[task_id],
                        role='system',
                        content=f"导入旧 AutonomySession：{row.get('title') or row.get('objective') or 'legacy autonomy'}",
                        metadata_={
                            'eventType': 'legacy-autonomy-session',
                            'legacyAutonomySessionId': str(row['id']),
                            'legacyData': {
                                'status': row.get('status'),
                                'repoPath': row.get('repo_path'),
                                'primaryAgentName': row.get('primary_agent_name'),
                                'primaryAgentType': row.get('primary_agent_type'),
                                'primaryAgentCommand': row.get('primary_agent_command'),
                                'maxIterations': row.get('max_iterations'),
                                'currentIteration': row.get('current_iteration'),
                                'interruptionCount': row.get('interruption_count'),
                                'successCriteria': row.get('success_criteria'),
                                'checkCommands': ensure_json(row.get('check_commands'), []),
                                'metadata': ensure_json(row.get('metadata'), {}),
                            },
                        },
                        created_at=to_datetime(row.get('created_at')),
                    ))
            else:
                report['skipped']['messages'] += 1

        for row in autonomy_cycle_rows:
            cycle_id = str(row['id'])
            session_id = str(row['session_id'])
            artifact_id = stable_uuid('legacy-autonomy-cycle-artifact', cycle_id)
            legacy_session = next((item for item in autonomy_session_rows if str(item['id']) == session_id), None)
            if not legacy_session:
                report['warnings'].append(f'AutonomyCycle {cycle_id} 找不到 session，已跳过。')
                continue
            task_id = str(legacy_session['task_id'])
            run_id = str(row['worker_run_id']) if row.get('worker_run_id') else None
            target_run_id = run_id if run_id and run_id in known_run_ids else None
            if target_run_id is None:
                synthetic_run_id = stable_uuid('legacy-autonomy-cycle-run', cycle_id)
                if session.get(Run, synthetic_run_id) is None:
                    report['created']['runs'] += 1
                    known_run_ids.add(synthetic_run_id)
                    if not dry_run:
                        message_id = stable_uuid('legacy-autonomy-cycle-message', cycle_id)
                        if session.get(Message, message_id) is None:
                            session.add(Message(
                                id=message_id,
                                thread_id=thread_ids_by_task[task_id],
                                role='system',
                                content=f"导入旧 AutonomyCycle：iteration {row.get('iteration')}",
                                metadata_={'eventType': 'legacy-autonomy-cycle', 'legacyAutonomyCycleId': cycle_id},
                                created_at=to_datetime(row.get('created_at')),
                            ))
                        session.add(Run(
                            id=synthetic_run_id,
                            thread_id=thread_ids_by_task[task_id],
                            message_id=message_id,
                            agent='custom',
                            status=map_run_status(row.get('status')),
                            round=int(row.get('iteration') or 1),
                            max_rounds=int(legacy_session.get('max_iterations') or 1),
                            error=(row.get('feedback_summary') or None),
                            metadata_={'legacy': {'source': 'autonomy_cycle', 'sessionId': session_id}},
                            created_at=to_datetime(row.get('created_at')),
                            completed_at=to_datetime(row.get('completed_at')),
                        ))
                else:
                    report['skipped']['runs'] += 1
                target_run_id = synthetic_run_id
            if session.get(ThreadRunArtifact, artifact_id) is None:
                report['created']['thread_run_artifacts'] += 1
                if not dry_run:
                    session.add(ThreadRunArtifact(
                        id=artifact_id,
                        run_id=target_run_id,
                        artifact_type='legacy_autonomy_cycle',
                        title=f"legacy autonomy cycle {row.get('iteration')}",
                        content=json.dumps({
                            'feedbackSummary': row.get('feedback_summary') or '',
                            'checkResults': ensure_json(row.get('check_results'), []),
                            'metadata': ensure_json(row.get('metadata'), {}),
                        }, ensure_ascii=False, indent=2),
                        path=None,
                        round=int(row.get('iteration') or 1),
                        metadata_={'legacy': {'source': 'autonomy_cycle', 'sessionId': session_id}},
                        created_at=to_datetime(row.get('created_at')),
                    ))
            else:
                report['skipped']['thread_run_artifacts'] += 1

        if dry_run:
            session.rollback()
        else:
            session.commit()

        report['legacyCounts'] = dict(report['legacyCounts'])
        report['created'] = dict(report['created'])
        report['skipped'] = dict(report['skipped'])
        return report
    finally:
        session.close()
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description='Migrate KAM v1 legacy tables into v2 tables.')
    parser.add_argument('--database-url', default=settings.DATABASE_URL)
    parser.add_argument('--apply', action='store_true', help='Persist migration result. Default is dry-run.')
    parser.add_argument('--backup-path', default=None)
    args = parser.parse_args()

    report = migrate(args.database_url, dry_run=not args.apply, backup_path=args.backup_path)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
