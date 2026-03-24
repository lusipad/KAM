# AI工作助手

一个面向开发内用的工作助手，定位是“外置大脑 + Agent 指挥台”。

它的目标不是做一个大而全的企业平台，而是先把开发工作里的几件核心事情接住：
- 记录任务、想法、链接和资料
- 为任务组装项目上下文
- 并发管理多个外部 Agent
- 收口 diff、日志、总结和后续建议

> 当前仓库已收敛到 `v1.2 Lite` 方向。Lite MVP 已经接上真实的 `Codex / Claude Code` CLI 执行链路，可直接在任务台里创建并发 runs、查看日志和收口结果。

## 当前状态

### 已实现
- Lite 任务台
  - 任务卡创建、更新、归档
  - 任务引用管理
  - 上下文快照生成
  - Agent run 创建、启动、取消、重试
  - review 汇总与 run artifacts 查看
  - run 维度 compare 结果
- 前端任务台页面
  - 任务列表
  - 引用录入
  - Context 查看
  - Agent runs 控制台
  - 运行状态自动刷新
  - 日志 / summary / prompt / context / changes / patch 查看
- 真实执行器
  - `Codex` CLI adapter
  - `Claude Code` CLI adapter
  - 自定义命令 adapter
  - `git worktree` 隔离工作目录（有 repo-path 引用时优先使用）
  - `git changes / patch` artifact 自动采集
- 历史模块仍保留
  - 笔记
  - 记忆
  - ClawTeam
  - Azure DevOps
  - 对话

### 尚未实现
- Run 日志实时流式 tail
- patch 自动回写 / 应用
- 复杂权限、多用户协作、审批流
- 默认开启的向量检索

## Lite MVP 主链路

当前最短可用链路是：

1. 创建任务卡
2. 给任务挂引用
3. 生成上下文快照
4. 为任务创建一个或多个 Agent run
5. 后端自动拉起 `Codex / Claude Code / custom command`
6. 查看 review summary、stdout/stderr、summary、changes、patch 等 artifacts

这条链路现在已经可用，run 会真实执行并把 `prompt / context / launch plan / stdout / stderr / summary / changes / patch` 回填到 artifacts。

## 技术栈

### 前端
- React 18 + TypeScript
- Vite
- Tailwind CSS + shadcn/ui
- Zustand
- Axios

### 后端
- FastAPI
- SQLAlchemy
- Pydantic Settings
- 轻量 Agent adapter
- `git worktree` 隔离执行目录

### 存储
- PostgreSQL 15
- pgvector 可选
- Redis 可选
- 本地 / Docker volume 文件存储

## 快速启动

### 方式一：Docker Compose

前提：
- Docker
- Docker Compose
- OpenAI API Key

步骤：

1. 复制环境变量文件
```bash
cp .env.example .env
```

PowerShell 可用：
```powershell
Copy-Item .env.example .env
```

2. 设置最少配置
```bash
OPENAI_API_KEY=your-openai-api-key
```

3. 启动服务
```bash
docker-compose up -d --build
```

4. 访问应用
- 前端: `http://localhost`
- 后端 API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

### 方式二：本地开发

前端：
```bash
cd app
npm install
npm run dev
```

后端：
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

说明：
- Docker Compose 默认使用 `PostgreSQL`
- 直接本地启动后端时，默认会使用 `sqlite:///./storage/dev.db`
- 若要启用真实 Agent runs，请确保本机已安装并可直接调用：
  - `codex`
  - `claude`

### Agent CLI 配置

默认配置：
```env
AGENT_WORKROOT=./storage/agent-runs
CODEX_CLI_PATH=codex
CLAUDE_CODE_CLI_PATH=claude
```

说明：
- `AGENT_WORKROOT` 用于存放每次 run 的 `prompt/context/log/summary`
- `CODEX_CLI_PATH` 和 `CLAUDE_CODE_CLI_PATH` 可以改成本机实际可执行文件路径
- `custom command` 在 Windows 下按 PowerShell 执行，在 Linux/macOS 下按 `bash/sh` 执行
- `custom command` 支持占位符：
  - `{run_dir}`
  - `{execution_cwd}`
  - `{prompt_file}`
  - `{context_file}`
- 若任务挂了 `repo-path` / `path` / `workspace` 类型引用，系统会优先尝试为 run 创建独立 `git worktree`

## 关键目录

```text
KAM/
├── app/                                  # 前端
│   └── src/
│       ├── components/Tasks/             # Lite 任务台页面
│       ├── components/Knowledge/         # 历史知识管理页面
│       ├── components/ClawTeam/          # 历史 ClawTeam 页面
│       ├── lib/api.ts                    # 前端 API 封装
│       ├── store/                        # 状态管理
│       └── types/                        # 前端类型
├── backend/
│   └── app/
│       ├── api/tasks.py                  # Lite 任务台 API
│       ├── models/workspace.py           # Lite 数据模型
│       ├── services/workspace_service.py # Lite 任务台服务
│       ├── api/                          # 其他历史 API
│       └── models/                       # 其他历史模型
├── MVP_BACKLOG.md                        # Lite MVP 拆解
├── AI工作助手产品需求文档(PRD).md
├── system_architecture.md
└── README.md
```

## API 概览

### Lite 任务台
- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `PUT /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/archive`
- `POST /api/tasks/{task_id}/refs`
- `POST /api/tasks/{task_id}/context/resolve`
- `POST /api/tasks/{task_id}/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `POST /api/runs/{run_id}/start`
- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/retry`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/reviews/{task_id}`
- `POST /api/reviews/{task_id}/compare`

### 历史 API
以下旧 API 仍保留：
- `/api/notes`
- `/api/memories`
- `/api/clawteam`
- `/api/ado`
- `/api/conversations`

## 文档

核心文档：
- [AI工作助手产品需求文档(PRD).md](./AI工作助手产品需求文档(PRD).md)
- [system_architecture.md](./system_architecture.md)
- [MVP_BACKLOG.md](./MVP_BACKLOG.md)

历史参考：
- [ai_work_assistant_architecture.md](./ai_work_assistant_architecture.md)
- [clawteam_technical_design.md](./clawteam_technical_design.md)
- [ai_memory_system_technical_proposal.md](./ai_memory_system_technical_proposal.md)

## 下一步

优先顺序建议：

1. 接真实 `Codex / Claude Code` adapter
2. 补 run 日志实时 tail / 流式输出
3. 补 patch 自动回写 / 应用能力
4. 补 ADO / Git 引用自动拉取
5. 只在确实需要时再加向量检索

## 备注

- 当前前端已能构建通过。
- Lite 任务主链路已经过 smoke test 验证，包含真实 custom command 执行。
- 仓库里仍保留一部分早期“知识管理 / 长期记忆 / ClawTeam”代码，它们和 Lite 架构并存，后续会逐步收敛。

## 许可证

MIT License
