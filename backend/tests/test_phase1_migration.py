import os
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import sessionmaker

os.environ['DATABASE_URL'] = 'sqlite:///./storage/test-phase1-migration.db'

from app.core.time import utc_now
from app.models.conversation import Message, Run, Thread, ThreadRunArtifact
from app.models.project import Project, ProjectResource
from scripts.legacy_schema import build_legacy_metadata, create_legacy_tables
from scripts.migrate_v1_to_v2 import migrate, stable_uuid
from scripts.verify_v1_to_v2 import verify


class Phase1MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'legacy-phase1.db'
        self.database_url = f'sqlite:///{self.db_path}'
        self.engine = create_engine(self.database_url, connect_args={'check_same_thread': False})
        create_legacy_tables(self.engine)
        self.metadata = build_legacy_metadata()
        self.metadata.reflect(bind=self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self._seed_legacy_data()

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_legacy_data(self):
        session = self.SessionLocal()
        try:
            now = utc_now()
            session.execute(insert(self.metadata.tables['task_cards']).values(
                id='task-1',
                title='重构认证模块',
                description='把认证模块升级到 OAuth2 + JWT',
                status='running',
                priority='high',
                tags=['auth', 'oauth'],
                metadata={'repoPath': '/repo/kam', 'checkCommands': ['pytest -q']},
                created_at=now,
                updated_at=now,
            ))
            session.execute(insert(self.metadata.tables['task_refs']).values(
                id='ref-1',
                task_id='task-1',
                ref_type='repo-path',
                label='主仓库',
                value='/repo/kam',
                metadata={'pinned': True},
                created_at=now,
            ))
            session.execute(insert(self.metadata.tables['context_snapshots']).values(
                id='snapshot-1',
                task_id='task-1',
                summary='已完成 token 签发，剩余 refresh',
                data={'recentFiles': ['auth/service.py']},
                created_at=now,
            ))
            session.execute(insert(self.metadata.tables['agent_runs']).values(
                id='run-1',
                task_id='task-1',
                agent_name='Codex',
                agent_type='codex',
                status='completed',
                workdir='/tmp/run-1',
                prompt='继续实现 refresh token',
                command='codex exec ...',
                error_message=None,
                metadata={'model': 'gpt-5.4', 'reasoningEffort': 'xhigh', 'round': 2, 'maxRounds': 5},
                created_at=now,
                started_at=now,
                completed_at=now,
            ))
            session.execute(insert(self.metadata.tables['run_artifacts']).values(
                id='artifact-1',
                run_id='run-1',
                artifact_type='summary',
                title='执行摘要',
                content='实现了 refresh token 逻辑',
                path=None,
                metadata={'round': 2},
                created_at=now,
            ))
            session.execute(insert(self.metadata.tables['autonomy_sessions']).values(
                id='session-1',
                task_id='task-1',
                title='认证模块自治会话',
                objective='完成 refresh token',
                status='completed',
                repo_path='/repo/kam',
                primary_agent_name='Codex',
                primary_agent_type='codex',
                primary_agent_command='codex exec ...',
                max_iterations=3,
                current_iteration=2,
                interruption_count=0,
                success_criteria='测试通过',
                check_commands=['pytest -q'],
                metadata={'dogfood': True},
                created_at=now,
                updated_at=now,
                completed_at=now,
            ))
            session.execute(insert(self.metadata.tables['autonomy_cycles']).values(
                id='cycle-1',
                session_id='session-1',
                iteration=2,
                status='passed',
                worker_run_id='run-1',
                feedback_summary='检查通过',
                check_results=[{'label': 'pytest', 'passed': True}],
                metadata={'source': 'autonomy'},
                created_at=now,
                completed_at=now,
            ))
            session.commit()
        finally:
            session.close()

    def test_migration_dry_run_does_not_create_v2_tables(self):
        report = migrate(self.database_url, dry_run=True)
        self.assertEqual(report['legacyCounts']['task_cards'], 1)

        session = self.SessionLocal()
        try:
            self.assertEqual(session.query(Project).count(), 0)
            self.assertEqual(session.query(Thread).count(), 0)
        finally:
            session.close()

    def test_migration_apply_and_verify(self):
        report = migrate(self.database_url, dry_run=False)
        self.assertEqual(report['created']['projects'], 1)
        self.assertEqual(report['created']['runs'], 1)

        verification = verify(self.database_url)
        self.assertTrue(verification['ok'], verification['errors'])

        session = self.SessionLocal()
        try:
            project = session.get(Project, 'task-1')
            self.assertIsNotNone(project)
            self.assertEqual(project.title, '重构认证模块')
            self.assertEqual(project.repo_path, '/repo/kam')

            resource = session.get(ProjectResource, 'ref-1')
            self.assertIsNotNone(resource)
            self.assertTrue(resource.pinned)

            thread = session.get(Thread, stable_uuid('legacy-thread', 'task-1'))
            self.assertIsNotNone(thread)

            run = session.get(Run, 'run-1')
            self.assertIsNotNone(run)
            self.assertEqual(run.status, 'passed')
            self.assertEqual(run.round, 2)

            artifact = session.get(ThreadRunArtifact, 'artifact-1')
            self.assertIsNotNone(artifact)
            self.assertEqual(artifact.artifact_type, 'summary')

            snapshot_message = session.get(Message, stable_uuid('legacy-snapshot-message', 'snapshot-1'))
            self.assertIsNotNone(snapshot_message)

            autonomy_message = session.get(Message, stable_uuid('legacy-autonomy-session-message', 'session-1'))
            self.assertIsNotNone(autonomy_message)

            autonomy_artifact = session.get(ThreadRunArtifact, stable_uuid('legacy-autonomy-cycle-artifact', 'cycle-1'))
            self.assertIsNotNone(autonomy_artifact)
        finally:
            session.close()


if __name__ == '__main__':
    unittest.main()
