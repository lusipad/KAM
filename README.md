# KAM Lite

KAM Lite 是一个面向开发场景的“外置大脑 + Agent 指挥台”。它只做一条核心链路：

1. 创建任务卡
2. 给任务添加引用
3. 生成 Context Snapshot
4. 并发拉起一个或多个 Agent run
5. 查看日志、summary、changes、patch
6. 在任务维度做 review 与 compare

当前仓库已经完成边界重置，只描述并实现 Lite Core。

## 保留能力

- Lite 任务台
- Context Snapshot
- Codex / Claude Code / custom command 执行链路
- `git worktree` 隔离运行目录
- run artifacts 查看
- review summary 与 compare
- SSE 事件流与轮询兜底

## 明确不做

- 额外独立工作台或管理台
- 平台内 patch apply
- 旧 API 兼容层
- 旧数据迁移

## 代码结构

```text
app/
  src/
    components/Layout/      Lite 壳层与设置
    components/Tasks/       唯一主工作台
    lib/api.ts              Lite Core API 客户端
    types/index.ts          Lite Core 类型

backend/
  app/api/tasks.py          Lite Core API
  app/models/workspace.py   任务/引用/快照/run/artifact 模型
  app/services/
    workspace_service.py    任务与收口服务
    run_executor.py         Agent 执行器
  scripts/reset_lite_core_schema.py
  tests/test_lite_core.py
```

## 本地开发

### 前端

```bash
cd app
npm install
npm run dev
```

### 后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

默认本地数据库为 `sqlite:///./storage/dev.db`。

## Docker

```bash
docker compose up -d --build
```

应用入口：

- UI: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

## Lite Core Schema Reset

需要直接清掉旧表和旧数据时，运行：

```bash
cd backend
python scripts/reset_lite_core_schema.py
```

该脚本会破坏式清空现有业务表，只重建以下 Lite Core 表：

- `task_cards`
- `task_refs`
- `context_snapshots`
- `agent_runs`
- `run_artifacts`

## 文档

- 主文档：
  - [README](README.md)
  - [PRD](AI工作助手产品需求文档(PRD).md)
  - [Architecture](system_architecture.md)
  - [Backlog](MVP_BACKLOG.md)
- 历史方案：
  - `docs/archive/legacy/`
