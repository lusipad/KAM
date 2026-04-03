# KAM Harness Cutover Status

> 这份文档不再把 V3 workspace 当目标态。
> 当前目标是：把 KAM 切到一个 `task-first`, `local-first`, `dogfood-first` 的软件工程 harness。

## 当前判断

- dogfood 验证基线：已稳定
- 最小 harness backend：已接上
- 默认前端入口：已切到 task-first workbench
- 旧 V3 workspace：仍在仓库中，但已退居过渡层

## 已完成

- 修复 `verify-local.ps1` 中的 SQLite lock，不再出现 `database is locked`
- 新增 Task 主链路：
  - `Task`
  - `TaskRef`
  - `ContextSnapshot`
  - `RunArtifact`
  - `ReviewCompare`
- 新增最小 harness API：
  - `/api/tasks`
  - `/api/tasks/{task_id}/refs`
  - `/api/tasks/{task_id}/context/resolve`
  - `/api/context/snapshots/{snapshot_id}`
  - `/api/tasks/{task_id}/runs`
  - `/api/runs/{run_id}/artifacts`
  - `/api/reviews/{task_id}/compare`
- harness run 已切成 task-native runtime，不再依赖 bridge project/thread
- 默认前端主入口改为 task-first workbench
- 新增 harness smoke
- 新增 `POST /api/dev/seed-harness`

## 当前仍有缺口

### 需要继续推进

- 彻底下掉旧 `projects / threads / home / watchers / memory` 主入口
- 把文档、脚本、命名进一步从 `v3 workspace` 语境切干净
- 补更完整的 task-first 前端交互：多任务切换、run 创建、compare 细化

### 明确不优先做

- 云化 / SaaS 化
- 多租户 / 账号体系
- 重型 watcher 主线
- 长期 memory 产品化

## 当前建议

- 继续沿 `KAM builds KAM` 方向推进，不要回到 V3 workspace 心智
- 下一步优先做旧入口退场和 task-first 交互补齐
- 所有新增能力都必须围绕 `Task -> Refs -> Snapshot -> Run -> Artifacts -> Compare`

## 对应文档

- 产品目标：[../product/ai_work_assistant_prd.md](../product/ai_work_assistant_prd.md)
- 当前 PRD：[../../.omx/plans/prd-harness-dogfood-cutover.md](../../.omx/plans/prd-harness-dogfood-cutover.md)
- 当前 Test Spec：[../../.omx/plans/test-spec-harness-dogfood-cutover.md](../../.omx/plans/test-spec-harness-dogfood-cutover.md)
