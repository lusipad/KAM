# KAM Phase 1 — 迁移执行 Runbook

## 1. Dry Run

```bash
cd backend
python3 -m scripts.migrate_v1_to_v2 --database-url sqlite:///./storage/dev.db
```

默认是 dry-run，只输出迁移报告，不落库。

## 2. 正式迁移

```bash
cd backend
python3 -m scripts.migrate_v1_to_v2 --database-url sqlite:///./storage/dev.db --apply
```

- SQLite 会先自动创建备份文件
- 旧表不会删除
- v2 表会自动补齐

## 3. 校验

```bash
cd backend
python3 -m scripts.verify_v1_to_v2 --database-url sqlite:///./storage/dev.db
```

返回 `ok: true` 才算通过。

## 4. 回滚

### SQLite

1. 停止服务
2. 用自动生成的 `.phase1-backup-*` 文件覆盖原库
3. 重新启动服务

### PostgreSQL

- 在正式迁移前先做逻辑备份或快照
- 迁移脚本本身不会删除旧表，因此可基于备份回滚

## 5. 验收清单

- `task_cards == projects`
- `task_refs == project_resources`
- `agent_runs == runs`
- `run_artifacts == thread_run_artifacts`（不低于旧数）
- 每个旧 task 都有默认 thread
- 每个旧 snapshot / autonomy session / autonomy cycle 都有新侧映射记录
