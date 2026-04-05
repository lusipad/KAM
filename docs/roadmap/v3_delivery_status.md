# KAM Harness Cutover Status

> 这份文档不再把 V3 workspace 当目标态。
> 当前目标是：把 KAM 切到一个 `task-first`, `local-first`, `dogfood-first` 的软件工程 harness。

## 当前判断

- dogfood 验证基线：已稳定
- 最小 harness backend：已接上
- 默认前端入口：已切到 task-first workbench
- task self-planning：已具备可执行 child task 能力
- V3 legacy runtime：已退场

## 已完成

- 修复 `verify-local.ps1` 中的 SQLite lock，不再出现 `database is locked`
- 新增 Task 主链路：
  - `Task`
  - `TaskRef`
  - `ContextSnapshot`
  - `TaskRunArtifact`
  - `ReviewCompare`
- 新增最小 harness API：
  - `/api/tasks`
  - `/api/tasks/{task_id}/refs`
  - `/api/tasks/{task_id}/context/resolve`
  - `/api/context/snapshots/{snapshot_id}`
  - `/api/tasks/{task_id}/runs`
  - `/api/runs/{run_id}/artifacts`
  - `/api/reviews/{task_id}/compare`
  - `/api/tasks/{task_id}/plan`
- harness run 已切成 task-native runtime，不再依赖 bridge project/thread
- 后端启动建库已切到 Alembic 升级链
- 默认前端主入口改为 task-first workbench
- 当前 task 已可基于 run、compare、snapshot、refs 和 artifacts 自动拆出并创建可执行的 follow-up tasks
- planner 生成的 child task 会自动带上推荐 Prompt、验收检查项和建议 refs，并可直接开跑
- 新增 harness smoke
- 新增 opt-in 真实 agent smoke（默认覆盖 `codex` 的临时 git repo 改动、Lore commit 和 adopt 链路）
- 新增 `POST /api/dev/seed-harness`
- 移除旧 `projects / threads / home / watchers / memory` 运行时入口
- 移除 V3 前端组件、类型层和验证基线
- 新增 Alembic head 迁移，正式下掉 legacy 表

## 当前仍有缺口

### 需要继续推进

- 把 task self-planning 从当前启发式继续做硬：引入更稳定的 repo/task 信号排序和更细的完成定义
- 把真实 `codex` 仓库改动链路稳固成默认 smoke 门禁
- 保留 `claude-code` 为可选 agent 和额外 smoke 目标，而不是默认主门禁

### 明确不优先做

- 云化 / SaaS 化
- 多租户 / 账号体系
- 重型 watcher 主线
- 长期 memory 产品化

## 当前建议

- 继续沿 `KAM builds KAM` 方向推进，不要回到 V3 workspace 心智
- 下一步优先把 task self-planning 继续做深，并把真实 `codex` 改仓库链路做成更硬的门禁
- 所有新增能力都必须围绕 `Task -> Refs -> Snapshot -> Run -> Artifacts -> Compare`

## 对应文档

- 产品目标：[../product/ai_work_assistant_prd.md](../product/ai_work_assistant_prd.md)
- 当前 PRD：[../../.omx/plans/prd-harness-dogfood-cutover.md](../../.omx/plans/prd-harness-dogfood-cutover.md)
- 当前 Test Spec：[../../.omx/plans/test-spec-harness-dogfood-cutover.md](../../.omx/plans/test-spec-harness-dogfood-cutover.md)
