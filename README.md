# KAM

KAM 现在的主目标不是继续做 V3 对话工作台，而是切到一个 `local-first` 的软件工程 agent harness，用 KAM 自己持续开发 KAM。

当前主链路：

`Task -> Refs -> Context Snapshot -> Runs -> Artifacts -> Review / Compare`

V3 workspace 相关代码仍在仓库里，但已经退到过渡层，不再代表新的产品中心。

## 当前状态

- 验证基线已稳定：`verify-local.ps1` 可通过
- 最小 harness backend 已接上：
  - `GET/POST /api/tasks`
  - `POST/DELETE /api/tasks/{task_id}/refs`
  - `POST /api/tasks/{task_id}/context/resolve`
  - `GET /api/context/snapshots/{snapshot_id}`
  - `POST /api/tasks/{task_id}/runs`
  - `GET /api/runs/{run_id}/artifacts`
  - `POST /api/reviews/{task_id}/compare`
- harness run 已是 task-native 存储，不再桥接到 `Project / Thread`
- 默认前端入口已切成 task-first workbench
- 开发态提供 harness demo 播种接口：`POST /api/dev/seed-harness`

## 目录

```text
app/
  src/
    features/tasks/      task-first workbench
    features/thread/     可复用的 Run 卡片等过渡组件
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

如果你要直接看 task-first 界面：

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/dev/seed-harness -Body (@{ reset = $true } | ConvertTo-Json) -ContentType 'application/json'
```

## 关键命令

后端单测：

```powershell
.\.venv\Scripts\python.exe -m unittest backend.tests.test_harness_api -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_v3_api -v
```

前端：

```powershell
Set-Location app
npm run build
npm run lint
npm run test:smoke:local
```

## 当前原则

- dogfood-first：先让 KAM 能稳定开发 KAM
- local-first：先把单机链路做硬，不先追云化
- task-first：不再以 thread/home/watcher/memory 作为产品中心
- prefer deletion：不为历史长期保留双主线
- legacy safety net：默认关闭 V3 主入口，但保留 `ENABLE_LEGACY_V3=true` 下的回归能力

## 参考文档

- [docs/README.md](./docs/README.md)
- [docs/product/ai_work_assistant_prd.md](./docs/product/ai_work_assistant_prd.md)
- [docs/roadmap/v3_delivery_status.md](./docs/roadmap/v3_delivery_status.md)
- [.omx/plans/prd-harness-dogfood-cutover.md](./.omx/plans/prd-harness-dogfood-cutover.md)
- [.omx/plans/test-spec-harness-dogfood-cutover.md](./.omx/plans/test-spec-harness-dogfood-cutover.md)
