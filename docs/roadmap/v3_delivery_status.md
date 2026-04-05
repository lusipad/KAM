# KAM Harness Cutover Status

> 这份文档不再把 V3 workspace 当目标态。
> 当前目标是：把 KAM 切到一个 `task-first`, `local-first`, `dogfood-first` 的软件工程 harness。

## 当前判断

- dogfood 验证基线：已稳定
- 最小 harness backend：已接上
- 默认前端入口：已切到 task-first workbench
- task self-planning：已具备显式信号排序和可执行 child task 能力
- task self-dispatch：已具备显式优先级调度
- task self-continue：已具备显式优先级调度
- task family auto-drive：已具备当前任务族级别的 opt-in 无人值守能力
- global backlog auto-drive：已具备跨 family、可重启恢复、跨进程 lease/dedupe，以及 cold-start chaos 回归覆盖的无人值守能力
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
  - `/api/tasks/dispatch-next`
  - `/api/tasks/continue`
- harness run 已切成 task-native runtime，不再依赖 bridge project/thread
- 后端启动建库已切到 Alembic 升级链
- 默认前端主入口改为 task-first workbench
- 当前 task 已可基于 run、compare、snapshot、refs 和 artifacts 自动拆出并创建可执行的 follow-up tasks
- planner 生成的 child task 会自动带上推荐 Prompt、验收检查项和建议 refs，并可直接开跑
- KAM 已可从现有任务池里自动接下一张任务；没有可跑 child task 时会先拆一张再开跑
- KAM 已可围绕当前 task family 自动继续推进：优先 `adopt / retry / plan_and_dispatch / stop`
- `dispatch-next / continue` 已切成显式 ranking：会稳定区分 `adopt / retry / existing runnable task / parent planning`，并优先处理强信号失败任务而不是弱 generic child
- 自动继续推进现在会尊重失败预算：同一任务连续失败达到上限后会显式 `paused/stop`，不再绕过 `retry` 限制继续重开 run
- planner follow-up 已切成显式 source ranking：会优先使用最新 terminal run / compare 信号，不再让旧失败 run 压过更新的通过结果
- KAM 已可对当前 task family 开启自动托管：run 完成后会继续复用 `continue_task()`，直到显式 `stop`
- 新增 `/api/tasks/{task_id}/autodrive/start` 与 `/api/tasks/{task_id}/autodrive/stop`
- KAM 已可开启全局无人值守：会跨 task family 继续接活，而不是只停留在单个 root task 上
- 新增 `/api/tasks/autodrive/global`、`/api/tasks/autodrive/global/start` 与 `/api/tasks/autodrive/global/stop`
- run 完成后会优先回到 global auto-drive；若未开启 global，才回落到当前 task family auto-drive
- 服务重启后会恢复 persisted global auto-drive，并把重启前残留的 `pending/running` runs 标记为中断失败，避免假活跃 run 卡死调度
- global auto-drive 已增加本地文件 lease：并发 KAM 进程会做 owner 去重、fresh lease 等待、stale lease 回收，避免重复接同一批活
- global auto-drive loop 遇到调度异常后会自动重试，而不是保持 enabled 但后台 supervisor 已退出
- global auto-drive 状态面板已返回结构化 lease / health 字段，能直接看到 owner、heartbeat、stale 与最近状态更新时间
- task family / global auto-drive 已返回 recent events，可直接回看等待、暂停、重启、错误与最近任务切换
- 已补真实多进程 lease 回归：验证第二个进程会被 active owner 挡住，owner 释放后新的进程可以接管
- 已补真实 crash failover 回归：持有 lease 的子进程被强制 kill 后，TTL 到期前仍会阻挡其他进程，TTL 到期后可自动接管
- 已补 cold-start chaos 回归：覆盖 `persisted enabled + stale lease reclaim`，以及 `persisted enabled + foreign lease wait -> TTL 后二次冷启动接管`
- global auto-drive supervisor 若被意外 cancel，只要全局开关仍开启，就会自动拉起新的 loop
- 前端已新增全局无人值守状态面板与开关
- 新增 harness smoke
- `verify-local.ps1` 已默认纳入真实 `codex` agent smoke，覆盖临时 git repo 改动、Lore commit 和 adopt 链路
- PR review comment monitor 已可把新评论写入 KAM 任务池，并自动拉起 global autodrive，而不是旁路直接执行
- 带远端执行目标的任务已可在指定 remote branch 上起 worktree、完成 run、push 回源分支，并自动把任务标记为 `verified`
- `claude-code` 作为可选 real smoke lane 已补 readiness 预检，会在 `claude auth status` 未就绪时提前失败，而不是跑到中途才报错
- 新增可配置的 global autodrive soak runner，并通过 `verify-local.ps1 -RunAutoDriveSoak` 暴露可选入口；它会持续注入 root task，校验长时轮询期间的进展信号与 recent events 有界性
- 新增 `run-autodrive-soak.ps1`，可把长时 soak 的 stdout、backend log、commit hash 与运行元数据自动归档到 `output/soak-runs/`
- 新增 `POST /api/dev/seed-harness`
- 移除旧 `projects / threads / home / watchers / memory` 运行时入口
- 移除 V3 前端组件、类型层和验证基线
- 新增 Alembic head 迁移，正式下掉 legacy 表

## 当前仍有缺口

### 需要继续推进

- 保留 `claude-code` 为可选 agent 和额外 smoke 目标，而不是默认主门禁
- 多小时级别无人值守 soak 现在已有脚本化入口，但仍需要在目标值守机器上实际跑够时长并留档

### 明确不优先做

- 云化 / SaaS 化
- 多租户 / 账号体系
- 重型 watcher 主线
- 长期 memory 产品化

## 当前建议

- 继续沿 `KAM builds KAM` 方向推进，不要回到 V3 workspace 心智
- 继续以 `verify-local.ps1` + 默认真实 `codex` smoke 作为主门禁，围绕当前 ranking 策略持续 dogfood
- 所有新增能力都必须围绕 `Task -> Refs -> Snapshot -> Run -> Artifacts -> Compare`

## 对应文档

- 产品目标：[../product/ai_work_assistant_prd.md](../product/ai_work_assistant_prd.md)
- 当前 PRD：[../../.omx/plans/prd-harness-dogfood-cutover.md](../../.omx/plans/prd-harness-dogfood-cutover.md)
- 当前 Test Spec：[../../.omx/plans/test-spec-harness-dogfood-cutover.md](../../.omx/plans/test-spec-harness-dogfood-cutover.md)
