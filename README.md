# KAM

KAM 是一个**可以长时间指挥 AI 工作的个人控制台**：围绕 `Project / Thread / Run / Memory` 组织持续上下文、并发执行与结果收口。

## 当前状态

当前仓库已经以 **v2 工作台** 为主：

- 前端默认直接进入 v2 工作区
- 后端默认以 `/api/v2` 作为主工作流接口
- Codex 默认模型已切到 `gpt-5.4` + `xhigh`
- Legacy Lite 能力仍保留在仓库中，作为迁移兼容与历史参考，不再是默认 UI

## v2 核心能力

- `Project`
  - 项目级描述、仓库路径、检查命令、资源钉住、归档
- `Thread`
  - 项目内连续对话与工作流
- `Run`
  - Codex / Claude Code / Custom Command 执行
  - 内置 artifacts、检查结果、失败反馈、重试、取消、采纳
- `Memory`
  - preferences / decisions / learnings / search
- `Compare`
  - 在同一 Thread 中并发发起多 Agent 对比

## 当前 UI

右侧主工作区已经补齐四块核心面板：

- `Project`：项目设置、资源管理、检查命令
- `Memory`：偏好、决策、项目 learnings、搜索
- `Detail`：Run artifacts、checks、命令与摘要
- `Compare`：多 Agent / custom command 并发对比

## API

主接口位于 `/api/v2`：

- `GET/POST /api/v2/projects`
- `GET/PUT /api/v2/projects/:id`
- `GET/POST/DELETE /api/v2/projects/:id/resources`
- `GET/POST /api/v2/projects/:id/threads`
- `GET /api/v2/threads/:id`
- `POST /api/v2/threads/:id/messages`
- `GET/POST /api/v2/threads/:id/runs`
- `POST /api/v2/threads/:id/compare`
- `GET /api/v2/runs/:id`
- `GET /api/v2/runs/:id/artifacts`
- `POST /api/v2/runs/:id/cancel|retry|adopt`
- `GET/POST/PUT /api/v2/memory/preferences`
- `GET/POST /api/v2/memory/decisions`
- `GET/POST /api/v2/memory/learnings`
- `GET /api/v2/memory/search`

## 代码结构

```text
app/
  src/
    components/Layout/         应用壳层与导航
    components/V2/             v2 主工作区
    lib/api-v2.ts              v2 API 客户端
    types/v2.ts                v2 类型定义

backend/
  app/api/
    projects.py                v2 项目 API
    threads.py                 v2 线程与消息 API
    runs.py                    v2 Run / Compare API
    memory.py                  v2 记忆 API
  app/services/
    conversation_router.py     对话路由
    context_assembler.py       上下文自动组装
    run_service.py             Run / Compare 服务
    run_engine.py              Run 生命周期与执行
    memory_service.py          记忆读写
  tests/test_v2_workspace.py     v2 回归测试
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

默认本地数据库：`sqlite:///./storage/dev.db`

## 验证

后端测试：

```bash
cd backend
python3 -m unittest discover -s tests -v
```

前端构建：

```bash
cd app
npm run build
```

## 文档

- `README.md`
- `system_architecture.md`
- `MVP_BACKLOG.md`
- `AI工作助手产品需求文档(PRD).md`
- `docs/autonomy-v2.md`
- `docs/archive/legacy/`
