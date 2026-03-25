# KAM Phase 1 — v1 到 v2 概念映射

## 映射表

| v1 | v2 | 说明 |
|---|---|---|
| `task_cards` | `projects` | 一对一映射，沿用同一 `id` |
| `task_refs` | `project_resources` | 一对一映射，沿用同一 `id` |
| `context_snapshots` | `messages` | 转为 `system` 消息，保留 `summary` 与 `data` |
| `agent_runs` | `runs` | 一对一映射，沿用同一 `id` |
| `run_artifacts` | `thread_run_artifacts` | 一对一映射，沿用同一 `id` |
| `autonomy_sessions` | `messages` | 转为 `system` 事件，原始字段保留在 `metadata` |
| `autonomy_cycles` | `thread_run_artifacts` | 转为 `legacy_autonomy_cycle` artifacts；如缺少对应 run，则生成 synthetic run |

## 补充对象

- 每个旧 `TaskCard` 自动生成一个默认 `Thread`
- 每个旧 `AgentRun` 自动生成一个导入消息，绑定到新的 `Run.message_id`
- `TaskCard.priority/tags/metadata` 保留到 `Project.settings.legacy`
- 无法一对一映射的旧自治字段保留到 `Message.metadata` 或 `ThreadRunArtifact.metadata`

## 状态映射

### Project

- `inbox/ready/running/review` -> `active`
- `paused/blocked/on-hold` -> `paused`
- `done/completed/archived` -> `done`

### Run

- `planned/queued` -> `pending`
- `running` -> `running`
- `completed/succeeded/success` -> `passed`
- `failed` -> `failed`
- `canceled/cancelled/interrupted` -> `cancelled`

## 不丢失策略

- 迁移后保留旧表，不做删除
- 所有无法直接映射的字段进入 `legacy` 元数据
- SQLite 正式迁移前自动备份数据库文件
