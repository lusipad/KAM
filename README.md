# KAM

KAM 现在的主目标不是继续做 V3 对话工作台，而是切到一个 `local-first` 的软件工程 agent harness，用 KAM 自己持续开发 KAM。

当前主链路：

`Task -> Refs -> Context Snapshot -> Runs -> Artifacts -> Review / Compare -> Follow-up Planning -> Next-Task Dispatch -> Continue`

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
  - `POST /api/tasks/dispatch-next`
  - `POST /api/tasks/continue`
- harness run 已是 task-native 存储
- 默认前端入口已切成 task-first workbench
- 当前 task 已可基于 run、compare、snapshot、refs 和 artifacts 自动拆出可执行的 follow-up tasks
- KAM 已可从任务池里自动接下一张任务；若当前没有可跑 child task，会先拆一张再开跑
- KAM 已可围绕当前 task family 自动继续推进：优先 `adopt / retry / plan_and_dispatch / stop`
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

如果你要显式验证 `claude-code` 这条可选 lane：

```powershell
pwsh -File .\verify-local.ps1 -RunRealAgentSmoke -RealSmokeAgent claude-code
```

这条链路现在会先做 `claude auth status` readiness 预检，未登录时会在真实 smoke 开始前直接失败。

如果你要补一轮更长时间的全局无人值守 soak：

```powershell
pwsh -File .\verify-local.ps1 -RunAutoDriveSoak -AutoDriveSoakMinutes 180
```

这条可选验证会启动独立 mock backend、持续注入新的 root task，并检查：

- 全局无人值守始终保持开启
- `recentEvents` 仍然有界
- loop 持续推进，不会长时间卡死
- 新注入 root task 最终能产出 follow-up task 和 passed run

如果你只想单独跑 soak runner，也可以直接执行：

```powershell
Set-Location .\app
$env:KAM_SOAK_DURATION_MS='10800000'
$env:KAM_SOAK_TASK_INTERVAL_MS='30000'
npm run test:soak:autodrive
```

如果你要直接看 task-first 界面：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/dev/seed-harness -Body (@{ reset = $true } | ConvertTo-Json) -ContentType 'application/json'
```

进入界面后，点击“让 KAM 自己排工作”会基于当前 task 的 run、compare、snapshot、refs 和 artifacts 自动拆出下一轮 follow-up tasks。拆出的子任务会自动带上推荐 Prompt、验收检查项和建议 refs，并支持直接开跑下一张任务。

点击“让 KAM 接下一张”时，KAM 会优先从现有任务池里挑选带推荐 Prompt 的可跑任务；如果当前还没有这样的 child task，就会先从最合适的父任务拆一张，再直接发起 run。

点击“继续推进当前任务”时，KAM 会先在当前 task family 内自动判断下一步：

- 有可自动采纳的真实 passed run 时，优先 `adopt`
- 有失败 child run 时，优先 `retry`
- 否则尝试 `plan_and_dispatch`
- 如果当前作用域已收口或仍有 run 在执行，就返回 `stop`

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
npm run test:soak:autodrive
```

安装 PR review comment 自动监控计划任务：

```powershell
pwsh -File .\install-pr-review-monitor.ps1 -Repo lusipad/KAM -PullRequest 4518
```

## 当前原则

- dogfood-first：先让 KAM 能稳定开发 KAM
- local-first：先把单机链路做硬，不先追云化
- task-first：只保留 `Task -> Refs -> Snapshot -> Run -> Artifacts -> Compare -> Plan -> Dispatch -> Continue`
- prefer deletion：不为历史长期保留双主线
- retire V3：旧 `projects / threads / home / watchers / memory` 已退场

## 参考文档

- [docs/README.md](./docs/README.md)
- [docs/product/ai_work_assistant_prd.md](./docs/product/ai_work_assistant_prd.md)
- [docs/roadmap/v3_delivery_status.md](./docs/roadmap/v3_delivery_status.md)
- [.omx/plans/prd-harness-dogfood-cutover.md](./.omx/plans/prd-harness-dogfood-cutover.md)
- [.omx/plans/test-spec-harness-dogfood-cutover.md](./.omx/plans/test-spec-harness-dogfood-cutover.md)
