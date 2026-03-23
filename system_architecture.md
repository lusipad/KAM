# AI工作助手 - 系统架构设计

## 1. 修订说明

### 1.1 v1.1 架构定位
本次修订将系统从“多个 AI 模块并列组合”调整为“工作流优先的上下文平台”。系统不取代 Azure DevOps、Git、Wiki 等既有业务系统，而是在其上构建统一的上下文层、执行层和治理层。

v1.1 的关键定义如下：
- 外部系统仍是事实源，平台负责聚合、增强和受控写回。
- ClawTeam 降级为内部执行引擎，不作为普通用户直接编排的主入口。
- 默认模式是读优先、写受控，写操作必须经过审批、审计和幂等保护。
- Prompt、评测、成本、权限、审计属于架构内建能力，不是后补功能。

### 1.2 架构原则

| 原则 | 说明 |
|------|------|
| **工作流优先** | 服务边界围绕高频闭环场景设计，而不是围绕“知识/记忆/代理”等概念单独堆模块 |
| **上下文统一组装** | 所有回答、草稿和执行动作都必须基于统一的 Context Service 组装上下文 |
| **外部系统为事实源** | ADO、Git、Wiki 等保留主系统地位，平台只做缓存、副本和增强 |
| **读优先写受控** | 读操作可自助，写操作必须经过审批、策略校验和写回记录 |
| **治理前置** | RBAC、审计、Prompt Registry、Eval、成本统计和密钥管理默认为基础设施 |
| **平台化复用** | 工作流、连接器、Prompt、审批策略和评测基线必须能在团队间复用 |

## 2. 目标架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI工作助手 v1.1 目标架构                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 入口层                                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 工作流工作台 | 对话入口 | 知识搜索 | 管理后台(连接器/审批/治理/评测)          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 应用服务层                                                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Workflow Orchestrator | Context Service | Knowledge/Memory Service          │
│ Connector Service | Approval Service | Writeback Service | Conversation API │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 执行与运行时层                                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ ClawTeam Execution Engine | Tool Registry | Async Worker | Retry/DLQ        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 治理与控制层                                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ Auth/SSO | RBAC | Policy Engine | Prompt Registry | Eval Service            │
│ Audit Log | Cost Control | Secret Management | Observability                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 数据与外部系统层                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ PostgreSQL + pgvector | Redis | Object Storage | Azure DevOps | Git/Wiki    │
│ LLM Providers | Identity Provider                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心服务职责

| 服务 | 职责 | 说明 |
|------|------|------|
| **Workflow Orchestrator** | 管理工作流模板、运行状态和步骤编排 | 决定是规则执行、单代理执行还是多代理执行 |
| **Context Service** | 汇聚知识、记忆、项目状态和历史执行结果 | 统一做权限裁剪、召回、重排序、上下文打包 |
| **Knowledge/Memory Service** | 管理笔记、记忆、摘要、索引和引用关系 | 既服务对话，也服务工作流 |
| **Connector Service** | 管理外部系统连接、同步游标、Webhook 和标准化数据模型 | 对 ADO/Git/Wiki 提供统一读取接口 |
| **Approval Service** | 管理审批策略、审批节点和人工接管 | 所有高风险写操作必须经过此服务 |
| **Writeback Service** | 负责外部系统草稿落地、幂等写入和补偿逻辑 | 不直接暴露给前端，必须由编排器调用 |
| **ClawTeam Execution Engine** | 承接复杂任务拆解、工具调用和结果综合 | 内部执行能力，不直接作为产品主模型暴露 |
| **Governance Plane** | 审计、Prompt 版本、评测、配额、成本和策略管理 | 贯穿整条执行链路 |

### 2.3 技术栈建议

| 领域 | 推荐选型 | 说明 |
|------|----------|------|
| **API与应用层** | Python 3.11+ + FastAPI | 统一同步/异步接口，适合快速迭代业务服务 |
| **工作流运行时** | LangGraph + Celery | 适配长链路编排、状态机和异步任务执行 |
| **连接器与同步** | HttpClient/官方 SDK + Webhook + 定时增量同步 | 兼顾实时性和可恢复性 |
| **主数据库** | PostgreSQL 15+ + pgvector | 结构化数据、JSONB 文档和向量统一管理 |
| **缓存与会话** | Redis | 热点缓存、短期上下文、分布式锁 |
| **对象存储** | MinIO / S3 | 附件、转写文件、归档结果 |
| **消息系统** | RabbitMQ | 工作流异步执行、重试和死信处理 |
| **LLM集成** | OpenAI / Azure OpenAI | 支持模型分级路由和企业网络要求 |
| **观测性** | OpenTelemetry + Prometheus + Grafana | 指标、日志、Tracing 一体化 |
| **身份与安全** | 企业 OIDC/SSO + Secret Manager | 对接企业身份体系和密钥托管 |

## 3. 数据库Schema

> 说明: 以下表结构主要是 v1.0 的功能基线，适合作为原型或单体版起点。若按 v1.1 目标架构落地到生产，至少还需要补充 `workflow_definitions`、`workflow_runs`、`workflow_steps`、`approval_requests`、`writeback_jobs`、`connector_cursors`、`audit_logs`、`prompt_versions`、`eval_runs`、`cost_usages`、`policy_bindings` 等治理与执行表。

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

v1.1 的 API 设计从“模块接口集合”改为“工作流和上下文驱动”。普通用户主要消费工作流、搜索、对话和审批接口；代理、模型和工具编排接口默认收敛为内部接口。

### 4.1 工作流API
```
GET    /api/workflows                          # 获取可用工作流模板
POST   /api/workflows/{workflow_id}/runs       # 启动一次工作流执行
GET    /api/workflow-runs/{run_id}             # 获取执行状态和步骤明细
POST   /api/workflow-runs/{run_id}/cancel      # 取消执行
POST   /api/workflow-runs/{run_id}/retry       # 重试失败步骤
GET    /api/workflow-runs/{run_id}/artifacts   # 获取草稿、引用、附件等产物
```

### 4.2 上下文与搜索API
```
POST   /api/context/resolve                    # 组装一次任务上下文
POST   /api/context/search                     # 跨知识/记忆/项目数据搜索
GET    /api/context/sources/{source_id}        # 查看引用源详情
GET    /api/context/entities/{type}/{id}       # 查看实体标准化视图
```

### 4.3 知识与对话API
```
GET    /api/notes
POST   /api/notes
GET    /api/notes/{id}
PUT    /api/notes/{id}
GET    /api/notes/search

GET    /api/conversations
POST   /api/conversations
GET    /api/conversations/{id}
POST   /api/conversations/{id}/messages        # 自动调用 Context Service 做增强
```

### 4.4 连接器与同步API
```
GET    /api/connectors                         # 获取连接器配置
POST   /api/connectors                         # 新增连接器
PUT    /api/connectors/{id}                    # 更新连接器
POST   /api/connectors/{id}/sync               # 触发增量同步
GET    /api/connectors/{id}/sync-jobs          # 查看同步任务
GET    /api/sources/ado/workitems              # 获取标准化后的工作项数据
```

### 4.5 审批与写回API
```
GET    /api/approvals                          # 获取审批列表
GET    /api/approvals/{id}                     # 获取审批详情
POST   /api/approvals/{id}/approve             # 审批通过
POST   /api/approvals/{id}/reject              # 审批拒绝
POST   /api/writebacks/{id}/execute            # 执行已审批写回
GET    /api/writebacks/{id}                    # 查看写回结果和回滚信息
```

### 4.6 治理与运营API
```
GET    /api/audit/logs                         # 审计日志
GET    /api/prompts                            # Prompt版本列表
POST   /api/evals/runs                         # 发起评测
GET    /api/cost/usage                         # 成本统计
GET    /api/policies                           # 权限和审批策略
```

## 5. 核心功能实现

### 5.1 上下文组装
```python
async def build_context(user, workflow_id, query, entity_refs):
    policy = await policy_engine.resolve(user=user, workflow_id=workflow_id)
    sources = await connector_service.resolve_entities(entity_refs, policy=policy)

    recalls = await context_service.hybrid_retrieve(
        query=query,
        sources=sources,
        include=["knowledge", "memory", "ado", "conversation_history"],
        top_k=20,
    )

    ranked = await context_service.rerank(query=query, candidates=recalls)
    packed = context_service.pack(
        ranked[:8],
        include_citations=True,
        token_budget=6000,
    )

    return packed
```

### 5.2 工作流执行
```python
async def run_workflow(workflow_id: str, payload: dict, user):
    workflow = await workflow_repo.load(workflow_id)
    context = await build_context(user, workflow_id, payload["query"], payload["refs"])

    plan = await orchestrator.plan(workflow=workflow, context=context, payload=payload)
    mode = "multi_agent" if plan.requires_decomposition else "single_agent"

    result = await execution_engine.execute(
        mode=mode,
        plan=plan,
        context=context,
        tool_policy=workflow.tool_policy,
    )

    await trace_service.record(run=plan.run_id, result=result)

    if result.contains_write_intent:
        return await approval_service.create_request(plan.run_id, result.write_draft)

    return result
```

### 5.3 受控写回
```python
async def execute_writeback(approval_id: str, operator):
    approval = await approval_service.ensure_approved(approval_id, operator=operator)
    job = await writeback_repo.create_job(
        approval_id=approval.id,
        idempotency_key=approval.idempotency_key,
    )

    response = await connector_runtime.write(
        system=approval.target_system,
        operation=approval.operation,
        payload=approval.payload,
        idempotency_key=job.idempotency_key,
    )

    await audit_log.record(
        action="writeback.execute",
        actor=operator.id,
        target=approval.target_ref,
        result=response.status,
    )

    if response.failed:
        await compensator.schedule(job.id)

    return response
```

## 6. 部署架构

```yaml
# docker-compose.yml
version: '3.8'

services:
  frontend:
    build: ./frontend
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
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - postgres
      - redis
      - rabbitmq

  worker:
    build: ./backend
    command: celery -A app.worker worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/ai_assistant
      - REDIS_URL=redis://redis:6379
      - RABBITMQ_URL=amqp://guest:guest@rabbitmq:5672/
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - postgres
      - redis
      - rabbitmq

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

  rabbitmq:
    image: rabbitmq:3-management
    ports:
      - "15672:15672"

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
RABBITMQ_URL=amqp://guest:guest@localhost:5672/

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

# 身份与治理
OIDC_ISSUER=https://idp.example.com
OIDC_CLIENT_ID=ai-work-assistant
OIDC_CLIENT_SECRET=...
APPROVAL_REQUIRED_SCOPES=ado.workitem.write,ado.comment.write
SECRET_PROVIDER=vault
PROMPT_REGISTRY_BACKEND=database
```
