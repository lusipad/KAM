# KAM

KAM 现在的主目标不是继续做 V3 对话工作台，而是切到一个 `local-first` 的软件工程 agent harness，用 KAM 自己持续开发 KAM。

当前主链路：

`Task -> Refs -> Context Snapshot -> Runs -> Artifacts -> Review / Compare`

V3 workspace 已经从运行时、前端主入口、验证基线和数据库 head 中退场。

## 当前状态

- 验证基线已稳定：`verify-local.ps1` 可通过
- 后端启动会执行 Alembic `upgrade head`，不再依赖 `create_all`
- 最小 harness backend 已接上：
  - `GET/POST /api/tasks`
  - `POST/DELETE /api/tasks/{task_id}/refs`
  - `POST /api/tasks/{task_id}/context/resolve`
  - `GET /api/context/snapshots/{snapshot_id}`
  - `POST /api/tasks/{task_id}/runs`
  - `GET /api/runs/{run_id}/artifacts`
  - `POST /api/reviews/{task_id}/compare`
  - `POST /api/tasks/{task_id}/plan`
- harness run 已是 task-native 存储
- 默认前端入口已切成 task-first workbench
- 当前 task 已可基于 run、compare、snapshot、refs 和 artifacts 自动拆出可执行的 follow-up tasks
- 开发态提供 harness demo 播种接口：`POST /api/dev/seed-harness`

## 目录

```text
app/
  src/
    features/tasks/      task-first workbench
    components/          task-first 复用组件
    layout/              壳层组件

backend/
  api/
    tasks.py
    context_snapshots.py
    reviews.py
    runs.py
  services/
    run_engine.py
    task_context.py
    artifact_store.py
    review_compare.py
  models.py
  main.py
  db.py

docs/
  product/              目标 PRD
  roadmap/              当前交付状态
  archive/legacy/       历史设计
```

## 本地开发

首次准备：

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r .\backend\requirements.txt
Set-Location .\app
npm install
Set-Location ..
```

启动：

```powershell
pwsh -File .\start-local.ps1
```

验证：

```powershell
pwsh -File .\verify-local.ps1
```

如果你要额外验证默认 `codex` 的真实 agent 执行链路：

```powershell
pwsh -File .\verify-local.ps1 -RunRealAgentSmoke -RealSmokeAgent codex
```

这条 smoke 现在会验证临时 git 仓库中的真实改动、Lore commit，以及 adopt 回主仓库的收口。

`codex` 是当前默认 agent。`claude-code` 仍保留为可选执行目标和额外 smoke 目标，但不是默认主门禁。

如果你要直接看 task-first 界面：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/dev/seed-harness -Body (@{ reset = $true } | ConvertTo-Json) -ContentType 'application/json'
```

进入界面后，点击“让 KAM 自己排工作”会基于当前 task 的 run、compare、snapshot、refs 和 artifacts 自动拆出下一轮 follow-up tasks。拆出的子任务会自动带上推荐 Prompt、验收检查项和建议 refs，并支持直接开跑下一张任务。

## 关键命令

后端单测：

```powershell
.\.venv\Scripts\python.exe -m unittest backend.tests.test_db_init -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_harness_api -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_task_planner_api -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_run_engine_lore -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_github_adapter -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_pr_review_monitor -v
```

前端：

```powershell
Set-Location app
npm run build
npm run lint
npm run test:smoke:local
npm run test:smoke:agent
```

安装 PR review comment 自动监控计划任务：

```powershell
pwsh -File .\install-pr-review-monitor.ps1 -Repo lusipad/KAM -PullRequest 4518
```

## 当前原则

- dogfood-first：先让 KAM 能稳定开发 KAM
- local-first：先把单机链路做硬，不先追云化
- task-first：只保留 `Task -> Refs -> Snapshot -> Run -> Artifacts -> Compare`
- prefer deletion：不为历史长期保留双主线
- retire V3：旧 `projects / threads / home / watchers / memory` 已退场

## 参考文档

- [docs/README.md](./docs/README.md)
- [docs/product/ai_work_assistant_prd.md](./docs/product/ai_work_assistant_prd.md)
- [docs/roadmap/v3_delivery_status.md](./docs/roadmap/v3_delivery_status.md)
- [.omx/plans/prd-harness-dogfood-cutover.md](./.omx/plans/prd-harness-dogfood-cutover.md)
- [.omx/plans/test-spec-harness-dogfood-cutover.md](./.omx/plans/test-spec-harness-dogfood-cutover.md)
