# AI工作助手 - 系统架构设计

## 1. 修订说明

### 1.1 v1.2 Lite 架构定位
本次修订将系统进一步收敛为“开发内用的外置大脑 + Agent 指挥台”。系统不追求复杂工作流平台、治理平台或知识平台形态，而是专注于把任务接住、把上下文组装好、把多个 Agent 调度起来，并把结果统一收口给人判断。

v1.2 Lite 的关键定义如下：
- 外部系统仍是事实源，平台负责读取、引用、增强和收口，不承担复杂审批写回。
- Agent 以外部 worker 形式接入，如 Codex、Claude Code，本系统负责调度而不是重造 Agent。
- 记忆以任务历史、笔记、上下文快照和摘要为主，不做复杂长期记忆治理。
- 技术栈坚持单库优先、少服务优先，优先保证本地和小团队能稳定使用。

### 1.2 架构原则

| 原则 | 说明 |
|------|------|
| **人主导** | 系统负责调度和整理，最终决策由人完成 |
| **任务优先** | 一切围绕任务卡、上下文、运行结果和复盘沉淀展开 |
| **外部 Agent 复用** | 优先复用现有成熟 Agent，通过 adapter 统一接入 |
| **最小复杂度** | 不为未来假想需求引入重型中间件和平台组件 |
| **文本优先** | 先靠笔记、链接、摘要、全文搜索解决问题，再考虑图谱和复杂记忆 |
| **逐步增强** | 向量检索、多用户权限、模板市场都放在真实需求出现后再加 |

## 2. 目标架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       AI工作助手 v1.2 Lite 目标架构                           │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 入口层                                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Inbox/任务台 | Agent Runs | Notes/Search | 对话入口                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 应用服务层                                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Task Service | Context Builder | Note Service | Connector Service            │
│ Agent Runner | Review Service | Conversation API                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 执行与运行时层                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Codex Adapter | Claude Code Adapter | Git Worktree Manager | Async Queue    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 数据与外部系统层                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ PostgreSQL | Redis(可选) | Local/Object Storage | Azure DevOps | Git/Docs   │
│ OpenAI / Anthropic / Local CLI                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心服务职责

| 服务 | 职责 | 说明 |
|------|------|------|
| **Task Service** | 管理收件箱、任务卡、状态流转和任务引用 | 系统的主入口和主对象 |
| **Context Builder** | 按任务聚合 ADO、代码、文档、笔记和历史运行结果 | 输出可传给 Agent 的上下文快照 |
| **Note Service** | 管理 Markdown 笔记、复盘、总结和常用 Prompt | 轻量记忆的主要载体 |
| **Connector Service** | 读取 ADO、Git、文档和本地文件 | 以只读和按需刷新为主 |
| **Agent Runner** | 启动、跟踪、停止和重试外部 Agent 运行 | 统一管理 Codex、Claude Code 等 worker |
| **Review Service** | 收集 patch、日志、命令输出和结论 | 方便人做比对和最终判断 |
| **Conversation API** | 在任务上下文基础上提供问答和解释能力 | 作为辅助入口，不是产品核心结构 |

### 2.3 技术栈建议

| 领域 | 推荐选型 | 说明 |
|------|----------|------|
| **API与应用层** | Python 3.11+ + FastAPI | 足够支撑 Lite 场景，开发效率高 |
| **前端工作台** | React 18 + TypeScript | 任务台、笔记、Agent Runs 面板 |
| **主数据库** | PostgreSQL 15+ | 任务、笔记、历史、上下文快照单库管理 |
| **可选向量** | pgvector | 仅在文档问答不足时启用 |
| **缓存/队列** | Redis | 可选，用于 run 状态和简单异步任务 |
| **Agent 适配** | Codex / Claude Code CLI + subprocess | 直接复用现成工具 |
| **工作区隔离** | git worktree | 支持多个 coding agent 并发执行 |
| **对象存储** | 本地目录 / MinIO | 保存附件、导出结果、日志 |
| **部署** | Docker Compose | 优先支持本地与小团队环境 |

## 3. 数据库Schema

> 说明: 以下表结构主要是 v1.0 的功能基线，适合作为原型或单体版起点。若按 v1.2 Lite 架构落地，建议优先补充 `task_cards`、`task_refs`、`agent_runs`、`run_artifacts`、`context_snapshots`、`run_logs` 等表；企业治理相关的审批、策略、评测和成本表可后置。

### notes 表
```sql
CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    content_type VARCHAR(20) DEFAULT 'markdown',
    path VARCHAR(1000) NOT NULL,
    version INTEGER DEFAULT 1,
    metadata JSONB DEFAULT '{}',
    stats JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 全文搜索索引
CREATE INDEX idx_notes_fts ON notes USING gin(to_tsvector('chinese', title || ' ' || content));
```

### links 表 (双向链接)
```sql
CREATE TABLE links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_note_id UUID REFERENCES notes(id) ON DELETE CASCADE,
    target_note_id UUID REFERENCES notes(id) ON DELETE CASCADE,
    link_type VARCHAR(20) DEFAULT 'wiki',
    context JSONB DEFAULT '{}',
    is_resolved BOOLEAN DEFAULT true,
    is_embed BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### memories 表 (长期记忆)
```sql
CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) DEFAULT 'default',
    memory_type VARCHAR(20) NOT NULL, -- fact, procedure, episodic
    category VARCHAR(100),
    content TEXT NOT NULL,
    content_vector VECTOR(1536), -- OpenAI embedding dimension
    summary TEXT,
    summary_vector VECTOR(1536),
    metadata JSONB DEFAULT '{}',
    context JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_accessed TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 向量相似度搜索索引
CREATE INDEX idx_memories_vector ON memories USING ivfflat (content_vector vector_cosine_ops);
```

### agents 表
```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    role VARCHAR(50) NOT NULL,
    description TEXT,
    capabilities JSONB DEFAULT '[]',
    system_prompt TEXT,
    model VARCHAR(100) DEFAULT 'gpt-4',
    temperature FLOAT DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2000,
    tools JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### agent_teams 表
```sql
CREATE TABLE agent_teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT,
    topology VARCHAR(50) DEFAULT 'hierarchical',
    coordinator_id UUID REFERENCES agents(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### team_agents 关联表
```sql
CREATE TABLE team_agents (
    team_id UUID REFERENCES agent_teams(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, agent_id)
);
```

### tasks 表
```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES agent_teams(id),
    description TEXT NOT NULL,
    goal TEXT,
    constraints JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'pending',
    priority INTEGER DEFAULT 5,
    result TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);
```

### subtasks 表
```sql
CREATE TABLE subtasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    complexity INTEGER DEFAULT 5,
    required_capabilities JSONB DEFAULT '[]',
    assigned_agent_id UUID REFERENCES agents(id),
    dependencies JSONB DEFAULT '[]',
    status VARCHAR(20) DEFAULT 'pending',
    expected_output TEXT,
    actual_output TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);
```

### ado_configs 表
```sql
CREATE TABLE ado_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    server_url VARCHAR(500) NOT NULL,
    collection VARCHAR(200) DEFAULT 'DefaultCollection',
    project VARCHAR(200) NOT NULL,
    auth_type VARCHAR(20) DEFAULT 'pat',
    credentials JSONB DEFAULT '{}',
    scopes JSONB DEFAULT '[]',
    is_active BOOLEAN DEFAULT true,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### conversations 表
```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) DEFAULT '新对话',
    context JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### messages 表
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL, -- user, assistant, system
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## 4. API设计

v1.2 Lite 的 API 设计从“模块接口集合”进一步收敛为“任务、上下文、Agent runs、笔记和集成”五类接口。重点是让任务能被创建、上下文能被组装、Agent 能被调度、结果能被回看。

### 4.1 任务API
```
GET    /api/tasks                              # 获取任务列表
POST   /api/tasks                              # 创建任务卡
GET    /api/tasks/{task_id}                    # 获取任务详情
PUT    /api/tasks/{task_id}                    # 更新任务
POST   /api/tasks/{task_id}/archive            # 归档任务
```

### 4.2 上下文与搜索API
```
POST   /api/tasks/{task_id}/context/resolve    # 为任务组装上下文
POST   /api/context/search                     # 搜索任务、笔记、历史结果、项目数据
GET    /api/context/sources/{source_id}        # 查看引用源详情
GET    /api/context/snapshots/{snapshot_id}    # 查看历史上下文快照
```

### 4.3 Agent Runs API
```
POST   /api/tasks/{task_id}/runs               # 启动一个或多个 Agent 运行
GET    /api/runs                               # 获取运行列表
GET    /api/runs/{run_id}                      # 获取运行详情
POST   /api/runs/{run_id}/cancel               # 中断运行
POST   /api/runs/{run_id}/retry                # 重试运行
GET    /api/runs/{run_id}/artifacts            # 查看 patch、日志、摘要等产物
```

### 4.4 笔记与对话API
```
GET    /api/notes
POST   /api/notes
GET    /api/notes/{id}
PUT    /api/notes/{id}
GET    /api/notes/search

GET    /api/conversations
POST   /api/conversations
POST   /api/conversations/{id}/messages        # 基于当前任务上下文做增强问答
```

### 4.5 连接器与外部系统API
```
GET    /api/connectors                         # 获取连接器配置
PUT    /api/connectors/{id}                    # 更新连接器
POST   /api/connectors/{id}/refresh            # 手动刷新当前连接
GET    /api/ado/workitems                      # 获取工作项
GET    /api/ado/pull-requests                  # 获取 PR
GET    /api/ado/builds                         # 获取构建状态
```

### 4.6 评审与收口API
```
GET    /api/reviews/{task_id}                  # 获取某任务的结果收口视图
POST   /api/reviews/{task_id}/summarize        # 汇总多个 Agent 结果
POST   /api/reviews/{task_id}/compare          # 对比多个 Agent 的结果
```

## 5. 核心功能实现

### 5.1 上下文组装
```python
async def build_task_context(task_id: str):
    task = await task_repo.get(task_id)
    refs = await task_repo.get_refs(task_id)

    project_data = await connector_service.fetch_refs(refs)
    related_notes = await note_service.search(task.title, limit=5)
    recent_runs = await run_repo.get_recent_by_task(task_id, limit=5)

    snapshot = {
        "task": task,
        "refs": project_data,
        "notes": related_notes,
        "recent_runs": recent_runs,
    }

    await context_repo.save_snapshot(task_id, snapshot)
    return snapshot
```

### 5.2 Agent 派发
```python
async def dispatch_agents(task_id: str, agents: list[str]):
    context = await build_task_context(task_id)
    runs = []

    for agent_name in agents:
        worktree = await git_manager.create_worktree(task_id, agent_name)
        run = await runner.start(
            agent=agent_name,
            task_id=task_id,
            context=context,
            workdir=worktree.path,
        )
        runs.append(run)

    return runs
```

### 5.3 结果收口
```python
async def collect_artifacts(task_id: str):
    runs = await run_repo.list_by_task(task_id)
    artifacts = []

    for run in runs:
        artifacts.extend(await artifact_repo.list_by_run(run.id))

    return review_service.summarize(
        task_id=task_id,
        artifacts=artifacts,
        include_diff=True,
        include_logs=True,
        include_risks=True,
    )
```

## 6. 部署架构

```yaml
# docker-compose.yml
version: '3.8'

services:
  frontend:
    build: ./app
    ports:
      - "80:80"
    depends_on:
      - backend

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/ai_assistant
      - REDIS_URL=redis://redis:6379
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - CODEX_CLI_PATH=/usr/local/bin/codex
      - CLAUDE_CODE_CLI_PATH=/usr/local/bin/claude
      - AGENT_WORKROOT=/workspace/agent-runs
    depends_on:
      - postgres
      - redis

  postgres:
    image: ankane/pgvector:latest
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=ai_assistant
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

## 7. 环境变量

```bash
# .env
# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/ai_assistant
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1

# Azure OpenAI (可选)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=...
AZURE_OPENAI_VERSION=2024-02-01

# 应用配置
APP_SECRET_KEY=your-secret-key
APP_DEBUG=false
APP_CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Agent 适配
CODEX_CLI_PATH=codex
CLAUDE_CODE_CLI_PATH=claude
AGENT_WORKROOT=./worktrees

# 外部系统
ADO_BASE_URL=https://ado.example.com
ADO_PAT=...
```
