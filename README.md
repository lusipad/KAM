# KAM Lite

KAM Lite 是一个面向开发场景的外置大脑与自治指挥台。它只保留一条核心工作链路，把开发任务从聊天上下文里拉回到可执行、可检查、可迭代的系统里。

## 核心工作链路

1. 创建 `TaskCard`
2. 给任务添加 `TaskRef`
3. 生成 `ContextSnapshot`
4. 拉起一个或多个 `AgentRun`
5. 查看 `prompt / context / stdout / stderr / summary / changes / patch`
6. 在任务维度做 `review / compare`
7. 进入 `AutonomySession`，让 AI 自动迭代并用检查命令自验收

当前仓库已经完成边界重置，只描述并实现 Lite Core 与自治闭环。

## 核心指标

- `autonomyCompletionRate`
  终态会话中，未被打断且最终完成的占比
- `interruptionRate`
  终态会话中，被用户显式打断的占比
- `successRate`
  终态会话中，最终通过检查并完成的占比
- `topFailedChecks`
  终态会话中最常见的失败检查项，用于识别系统瓶颈

指标、术语与文档写法的标准口径以 [Documentation Standards](docs/documentation-standards.md) 为准。

## 保留能力

- Lite 任务台
- Context Snapshot
- `codex` / `claude-code` / `custom command` 执行链路
- `git worktree` 隔离运行目录
- run artifacts 查看
- review summary 与 compare
- SSE 事件流与轮询兜底
- `AutonomySession / AutonomyCycle`
- 任务级与全局自治指标
- KAM 仓库 `dogfooding` 模板
- 优化战役脚本与报告输出

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
  app/api/autonomy.py       自治会话 API
  app/models/workspace.py   任务/引用/快照/run/artifact 模型
  app/services/
    workspace_service.py    任务与收口服务
    run_executor.py         Agent 执行器
    autonomy_service.py     自治会话与指标服务
    autonomy_manager.py     自治迭代与检查执行器
  scripts/reset_lite_core_schema.py
  scripts/run_optimization_campaign.py
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
- `autonomy_sessions`
- `autonomy_cycles`

## 文档地图

| 文档 | 作用 | 何时阅读 |
| --- | --- | --- |
| [README](README.md) | 仓库入口、边界与启动方式 | 第一次进入仓库时 |
| [PRD](<AI工作助手产品需求文档(PRD).md>) | 产品目标、范围、验收标准 | 判断需求是否偏航时 |
| [Architecture](system_architecture.md) | 组件、模型、执行路径、指标来源 | 做系统改动前 |
| [Autonomy V2](docs/autonomy-v2.md) | 自治闭环设计与操作口径 | 做自治相关功能前 |
| [Optimization Campaign](docs/optimization-campaign.md) | 战役脚本、执行方式、结果解释 | 跑 10 任务样本前 |
| [Documentation Standards](docs/documentation-standards.md) | 术语、章节结构、内容规范 | 改文档前 |
| [Autonomy Optimization Report 2026-03-25](docs/campaigns/2026-03-25-autonomy-optimization-report.md) | 已实跑战役结果与结论 | 评估当前进展时 |
| [Backlog](MVP_BACKLOG.md) | 当前优先级与后续路线 | 安排下一轮开发时 |

历史方案保留在 `docs/archive/legacy/`。
