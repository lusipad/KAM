# KAM V3

KAM V3 是一个三栏 AI 工作台：左侧是按项目分组的线程导航，中间是 Home feed / Thread 对话，右侧是随时可展开的 Memory panel。主线 API 已切到 `/api/*`，本地默认运行新的 `backend/main.py`。

## 当前主线

- 三栏工作台
  - Sidebar：活跃任务摘要、项目分组线程、Home / Watchers / Memory 入口
  - Main：Empty state、Home feed、Thread conversation、Watcher 管理
  - Memory：按偏好 / 决策 / learnings / project context 展示
- V3 后端
  - `Project / Thread / Message / Run / Memory / Watcher / WatcherEvent`
  - 首条输入通过服务端 bootstrap 自动创建 Project / Thread，并生成标题
  - SSE 事件推送
  - Run adopt / retry
  - Watcher draft / activate / run-now / pause / resume / action / dismiss
- 运行方式
  - 后端直接服务前端构建产物
  - 默认数据库：`sqlite+aiosqlite:///./storage/kam-v3.db`
  - Alembic 迁移链已重置为 V3 baseline

## 目录

```text
app/
  src/
    layout/            三栏壳层
    features/home/     Home feed
    features/thread/   对话流、Run 卡片、输入框
    features/review/   PR review 卡片
    features/memory/   右侧记忆面板
    features/watcher/  Watcher 管理

backend/
  main.py              FastAPI 入口
  config.py            V3 settings
  db.py                async engine / session / init_db
  models.py            V3 SQLAlchemy 模型
  api/                 /api 路由
  services/            router / run / digest / watcher / memory
  adapters/            GitHub / Azure / CI 适配器
  alembic/             V3 baseline migration

docs/
  README.md            文档索引
  product/             产品需求与定位
  design/              设计稿、架构稿、UI 规范
  roadmap/             路线图与执行计划
  migration/           迁移文档
  archive/legacy/      历史方案归档
  archive/notes/       历史探针与临时记录
```

## 本地开发

### 一键本地预览

```bash
./start-local.sh
```

Windows PowerShell:

```powershell
pwsh -File .\start-local.ps1
pwsh -File .\verify-local.ps1
pwsh -File .\seed-demo.ps1
```

这个脚本会先构建前端，再启动：

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 分开运行

前端构建：

```bash
cd app
npm install
npm run build
```

后端启动：

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

打开 `http://localhost:8000`。

## Docker

```bash
./start.sh
```

Windows PowerShell:

```powershell
pwsh -File .\start.ps1
pwsh -File .\start.ps1 -Port 8012
```

Docker 版本会：

- 构建 `app/dist`
- 在单个容器内运行 `backend/main.py`
- 使用挂载卷持久化 `backend/storage`

## API

主接口位于 `/api`：

- `GET/POST /api/projects`
- `POST /api/projects/bootstrap`
- `POST /api/projects/{project_id}/threads`
- `GET /api/threads`
- `GET /api/threads/{thread_id}`
- `POST /api/threads/{thread_id}/messages`
- `GET /api/threads/{thread_id}/events`
- `GET /api/home/feed`
- `GET /api/home/events`
- `GET/POST /api/memory`
- `GET /api/watchers`
- `POST /api/watchers`
- `POST /api/watchers/{watcher_id}/pause`
- `POST /api/watchers/{watcher_id}/activate`
- `POST /api/watchers/{watcher_id}/resume`
- `POST /api/watchers/{watcher_id}/run-now`
- `POST /api/watchers/events/{event_id}/actions/{action_index}`
- `POST /api/watchers/events/{event_id}/dismiss`
- `POST /api/runs/{run_id}/retry`
- `POST /api/runs/{run_id}/adopt`

开发态还提供一条 demo 数据播种接口：

- `POST /api/dev/seed-demo`

## 验证

后端：

```bash
python -m unittest backend.tests.test_v3_api -v
```

前端：

```bash
cd app
npm run build
npm run lint
```

浏览器 smoke：

```bash
cd app
npm run test:smoke
npm run test:smoke:local
```

`test:smoke` 会先调用 `/api/dev/seed-demo`，再验收 Home / Thread / Memory / Watchers 四个 V3 关键视图。运行时需要目标服务已经启动，默认地址是 `http://127.0.0.1:8000`，也可以通过 `PW_BASE_URL` 覆盖。

`test:smoke:local` 会自动起一个临时后端实例，使用 `backend/storage/smoke-v3.db` 跑完整浏览器 smoke，结束后自动收尾。

`verify-local.ps1` 会依次执行后端单测、前端 build、lint 和本地 smoke。

## 当前交互约定

- 新对话不再在前端本地裁剪标题，而是调用服务端 `bootstrap` 生成项目和线程标题。
- 对话里创建的 watcher 会先以 `draft` 草稿卡片出现，用户可直接在当前线程里编辑细节并启用。
- Home feed 的“需要你处理”按统一优先级混排：失败 run、watcher 提醒、等待采纳结果。

## 规范来源

- [`docs/README.md`](docs/README.md)
- [`docs/product/ai_work_assistant_prd.md`](docs/product/ai_work_assistant_prd.md)
- [`docs/design/v3_architecture_design.md`](docs/design/v3_architecture_design.md)
- [`docs/design/v3_ui_spec.md`](docs/design/v3_ui_spec.md)
- [`docs/roadmap/v2_implementation_roadmap.md`](docs/roadmap/v2_implementation_roadmap.md)
