# KAM v2 — Complete Technical Design

> AI 外置大脑 + AI 控制中心。从零开始的完整设计。
> 核心原则：用户唯一的操作是打字。其他一切由 AI 决定。

---

## 1. 项目结构

```
kam/
├── backend/
│   ├── main.py                  # FastAPI app + lifespan（启动 scheduler）
│   ├── config.py                # Settings（Pydantic BaseSettings）
│   ├── db.py                    # SQLAlchemy async engine + session
│   ├── models.py                # 所有数据模型（一个文件，<200 行）
│   ├── events.py                # EventBus（in-process asyncio.Queue）
│   ├── services/
│   │   ├── router.py            # ConversationRouter — 对话 AI 核心
│   │   ├── run_engine.py        # RunEngine — Claude Code / Codex 执行
│   │   ├── memory.py            # MemoryService — 记忆读写 + 检索 + 衰减
│   │   ├── context.py           # ContextAssembler — 组装 LLM 上下文
│   │   ├── watcher.py           # WatcherEngine — 定时监控 + 触发
│   │   ├── action.py            # ActionEngine — 写回外部系统
│   │   └── digest.py            # DigestService — Run/Watcher 结果 AI 摘要
│   ├── adapters/
│   │   ├── github.py            # GitHub API adapter（ghapi）
│   │   ├── azure_devops.py      # Azure DevOps adapter
│   │   └── ci.py                # CI pipeline adapter（GitHub Actions 等）
│   └── api/
│       ├── threads.py           # Thread CRUD + SSE 事件流
│       ├── runs.py              # Run 创建 + adopt + 状态
│       ├── watchers.py          # Watcher CRUD + pause/resume
│       ├── memory_api.py        # Memory 查看 + 手动编辑
│       └── home.py              # Home feed 聚合
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── layout/
│   │   │   ├── AppShell.tsx     # 三栏布局骨架
│   │   │   └── Sidebar.tsx      # 对话历史 + 状态指示器
│   │   ├── features/
│   │   │   ├── home/
│   │   │   │   └── HomeFeed.tsx # 任务总览（需关注 / 运行中 / 历史）
│   │   │   ├── thread/
│   │   │   │   ├── ThreadView.tsx
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   ├── MessageInput.tsx
│   │   │   │   └── RunCard.tsx  # 4 种状态：pending/running/passed/failed
│   │   │   ├── review/
│   │   │   │   └── ReviewCommentCard.tsx  # PR review 评论卡片
│   │   │   ├── memory/
│   │   │   │   └── MemoryPanel.tsx        # 右侧滑入面板
│   │   │   └── watcher/
│   │   │       └── WatcherList.tsx        # Watcher 管理列表
│   │   ├── hooks/
│   │   │   ├── useSSE.ts        # SSE 订阅 hook
│   │   │   └── useHomeFeed.ts   # 聚合 feed 数据
│   │   └── api/
│   │       └── client.ts        # HTTP + SSE 客户端
│   └── index.html
├── alembic/                     # DB 迁移
├── requirements.txt
├── package.json
└── README.md
```

---

## 2. 依赖

### Python（backend/requirements.txt）

```
# Core
fastapi>=0.115
uvicorn[standard]>=0.32
pydantic>=2.0
pydantic-settings>=2.0

# Database
sqlalchemy[asyncio]>=2.0
aiosqlite>=0.20
alembic>=1.14

# AI
anthropic>=0.42
tiktoken>=0.8

# Real-time + Scheduling
sse-starlette>=2.1
apscheduler>=4.0

# Git + External APIs
gitpython>=3.1
ghapi>=1.0
httpx>=0.27

# Azure DevOps（按需）
# azure-devops>=7.1
```

### Node（frontend/package.json — 核心依赖）

```json
{
  "dependencies": {
    "react": "^19",
    "react-dom": "^19",
    "react-router-dom": "^7"
  },
  "devDependencies": {
    "vite": "^6",
    "typescript": "^5.7",
    "@types/react": "^19"
  }
}
```

---

## 3. 配置

```python
# backend/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./kam.db"

    # AI
    anthropic_api_key: str = ""
    chat_model: str = "claude-sonnet-4-20250514"      # 对话 + triage
    digest_model: str = "claude-sonnet-4-20250514"     # Run 摘要（便宜快速）

    # Agent CLIs
    claude_code_path: str = "claude"   # Claude Code CLI
    codex_path: str = "codex"          # Codex CLI

    # External APIs（按需配置）
    github_token: str = ""
    azure_devops_pat: str = ""
    azure_devops_org: str = ""

    # Limits
    context_budget_tokens: int = 8000      # 总 context 预算
    memory_always_inject_tokens: int = 500 # 始终注入的记忆预算
    memory_search_tokens: int = 1500       # 按需检索的记忆预算
    max_concurrent_runs: int = 3

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 4. 数据库

### 4.1 引擎与会话

```python
# backend/db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        yield session
```

### 4.2 数据模型

```python
# backend/models.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Text, JSON, Float, DateTime, Integer, ForeignKey, Boolean, Index
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

def new_id() -> str:
    return uuid.uuid4().hex[:12]

def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ─── Project ────────────────────────────────────────────────────
class Project(Base):
    """
    项目 = 一个工作上下文。可以绑定仓库，也可以是纯对话型。
    由 AI 在用户首次提到相关工作时自动创建。
    """
    __tablename__ = "projects"

    id:         Mapped[str]  = mapped_column(String(12), primary_key=True, default=new_id)
    title:      Mapped[str]  = mapped_column(String(200))
    repo_path:  Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime]   = mapped_column(DateTime, default=now)

    threads:  Mapped[list["Thread"]]  = relationship(back_populates="project")
    memories: Mapped[list["Memory"]]  = relationship(back_populates="project")
    watchers: Mapped[list["Watcher"]] = relationship(back_populates="project")


# ─── Thread ─────────────────────────────────────────────────────
class Thread(Base):
    """
    一个对话线程。标题由 AI 生成。
    external_ref 绑定外部实体（如 PR、Issue），让 Watcher 事件能注入正确的 thread。
    """
    __tablename__ = "threads"

    id:           Mapped[str]  = mapped_column(String(12), primary_key=True, default=new_id)
    project_id:   Mapped[str]  = mapped_column(ForeignKey("projects.id"))
    title:        Mapped[str]  = mapped_column(String(200), default="New conversation")
    external_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # external_ref 示例：{"type": "github_pr", "repo": "org/repo", "number": 231}
    created_at:   Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at:   Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    project:  Mapped["Project"]       = relationship(back_populates="threads")
    messages: Mapped[list["Message"]] = relationship(back_populates="thread", order_by="Message.created_at")
    runs:     Mapped[list["Run"]]     = relationship(back_populates="thread")


# ─── Message ────────────────────────────────────────────────────
class Message(Base):
    """
    对话消息。role = user | assistant | system。
    metadata 存附加信息（如 generated_by: run-digest, watcher-alert）。
    """
    __tablename__ = "messages"

    id:         Mapped[str]  = mapped_column(String(12), primary_key=True, default=new_id)
    thread_id:  Mapped[str]  = mapped_column(ForeignKey("threads.id"))
    role:       Mapped[str]  = mapped_column(String(20))  # user | assistant | system
    content:    Mapped[str]  = mapped_column(Text)
    metadata_:  Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime]    = mapped_column(DateTime, default=now)

    thread: Mapped["Thread"] = relationship(back_populates="messages")


# ─── Run ────────────────────────────────────────────────────────
class Run(Base):
    """
    一次 Agent 执行（Claude Code / Codex）。
    status 流转：pending → running → passed | failed | cancelled
    """
    __tablename__ = "runs"

    id:           Mapped[str]  = mapped_column(String(12), primary_key=True, default=new_id)
    thread_id:    Mapped[str]  = mapped_column(ForeignKey("threads.id"))
    agent:        Mapped[str]  = mapped_column(String(30))  # claude-code | codex | custom
    status:       Mapped[str]  = mapped_column(String(20), default="pending")
    task:         Mapped[str]  = mapped_column(Text)    # AI 生成的任务描述
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI 生成的结果摘要
    changed_files:  Mapped[list | None] = mapped_column(JSON, nullable=True)
    check_passed:   Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    duration_ms:    Mapped[int | None]  = mapped_column(Integer, nullable=True)
    worktree_path:  Mapped[str | None]  = mapped_column(String(500), nullable=True)
    adopted_at:     Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    raw_output:     Mapped[str | None] = mapped_column(Text, nullable=True)  # stdout tail
    created_at:     Mapped[datetime]   = mapped_column(DateTime, default=now)

    thread: Mapped["Thread"] = relationship(back_populates="runs")


# ─── Memory ─────────────────────────────────────────────────────
class Memory(Base):
    """
    AI 的记忆。四种类别：preference, decision, fact, learning。
    relevance_score 控制衰减：被引用加分，不用减分。
    superseded_by 处理矛盾：新记忆覆盖旧记忆时，旧记忆不删除而是标记。
    """
    __tablename__ = "memories"

    id:              Mapped[str]  = mapped_column(String(12), primary_key=True, default=new_id)
    project_id:      Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    scope:           Mapped[str]  = mapped_column(String(20), default="project")  # global | project
    category:        Mapped[str]  = mapped_column(String(20))  # preference | decision | fact | learning
    content:         Mapped[str]  = mapped_column(Text)
    rationale:       Mapped[str | None] = mapped_column(Text, nullable=True)  # WHY, not just WHAT
    relevance_score: Mapped[float] = mapped_column(Float, default=1.0)
    superseded_by:   Mapped[str | None] = mapped_column(String(12), nullable=True)
    source_thread_id:  Mapped[str | None] = mapped_column(String(12), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime, default=now)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    project: Mapped["Project | None"] = relationship(back_populates="memories")

    __table_args__ = (
        Index("ix_memory_project_category", "project_id", "category"),
        Index("ix_memory_relevance", "relevance_score"),
    )


# ─── Watcher ────────────────────────────────────────────────────
class Watcher(Base):
    """
    自动化监视器。定时拉取外部数据源，AI 分析后注入 Home feed。
    source_type: github_pr | azure_devops | ci_pipeline | repo_scan
    schedule_type: interval | cron | webhook
    """
    __tablename__ = "watchers"

    id:             Mapped[str]  = mapped_column(String(12), primary_key=True, default=new_id)
    project_id:     Mapped[str]  = mapped_column(ForeignKey("projects.id"))
    name:           Mapped[str]  = mapped_column(String(200))
    source_type:    Mapped[str]  = mapped_column(String(50))
    config:         Mapped[dict] = mapped_column(JSON)  # 源特定配置
    # config 示例 (github_pr):
    # {"repo": "org/repo", "watch": "assigned_prs", "filter_user": "me"}
    # config 示例 (ci_pipeline):
    # {"repo": "org/repo", "branch": "main", "provider": "github_actions"}
    schedule_type:  Mapped[str]  = mapped_column(String(20))  # interval | cron
    schedule_value: Mapped[str]  = mapped_column(String(50))  # "15m" | "0 9 * * *"
    status:         Mapped[str]  = mapped_column(String(20), default="active")  # active | paused
    auto_action_level: Mapped[int] = mapped_column(Integer, default=1)
    # 0=notify only, 1=triage+draft, 2=auto-fix, 3=full autopilot
    last_run_at:    Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_state:     Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # last_state 存上次拉取的状态快照，用于 diff
    created_at:     Mapped[datetime] = mapped_column(DateTime, default=now)

    project: Mapped["Project"] = relationship(back_populates="watchers")


# ─── WatcherEvent ───────────────────────────────────────────────
class WatcherEvent(Base):
    """
    Watcher 产生的事件。出现在 Home feed 里。
    status: pending（需要关注）| handled（已处理）| dismissed（忽略）
    """
    __tablename__ = "watcher_events"

    id:          Mapped[str]  = mapped_column(String(12), primary_key=True, default=new_id)
    watcher_id:  Mapped[str]  = mapped_column(ForeignKey("watchers.id"))
    thread_id:   Mapped[str | None] = mapped_column(ForeignKey("threads.id"), nullable=True)
    event_type:  Mapped[str]  = mapped_column(String(50))  # new_pr_comments | ci_failed | new_tasks ...
    title:       Mapped[str]  = mapped_column(String(300))
    summary:     Mapped[str]  = mapped_column(Text)    # AI 生成的摘要
    raw_data:    Mapped[dict] = mapped_column(JSON)    # 原始数据
    actions:     Mapped[list | None] = mapped_column(JSON, nullable=True)
    # actions 示例: [{"label": "Auto-fix", "action": "run", "params": {...}}, ...]
    status:      Mapped[str]  = mapped_column(String(20), default="pending")
    created_at:  Mapped[datetime] = mapped_column(DateTime, default=now)

    watcher: Mapped["Watcher"]       = relationship()
    thread:  Mapped["Thread | None"] = relationship()
```

---

## 5. EventBus

```python
# backend/events.py
"""
In-process 事件总线。单进程单用户，asyncio.Queue 足够。
不需要 Redis / RabbitMQ。

用法：
  - RunEngine 发布 run 进度  → 前端 SSE 实时更新
  - WatcherEngine 发布事件   → Home feed 刷新
  - DigestService 发布摘要   → Thread 追加消息
"""
import asyncio
from collections import defaultdict
from typing import Any

class EventBus:
    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._channels[channel].append(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue):
        if q in self._channels[channel]:
            self._channels[channel].remove(q)

    def publish(self, channel: str, event: dict[str, Any]):
        for q in list(self._channels.get(channel, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # 丢弃旧事件，不阻塞发布者

    async def publish_async(self, channel: str, event: dict[str, Any]):
        """从 async 上下文发布，允许等待队列空间"""
        for q in list(self._channels.get(channel, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

# 全局单例
event_bus = EventBus()
```

---

## 6. 核心服务

### 6.1 ConversationRouter — 对话 AI 核心

```python
# backend/services/router.py
"""
核心对话引擎。用户的每条消息都经过这里。

职责：
1. 组装 context（记忆 + 历史 + 项目状态）
2. 调用 Anthropic SDK（streaming + tool_use）
3. 流式回复推送给前端
4. 处理 tool calls：create_run / record_memory / create_watcher
"""
import anthropic
from config import settings
from services.context import ContextAssembler
from services.memory import MemoryService
from events import event_bus

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

# ─── Tool 定义 ────────────────────────────────────────────────
TOOLS = [
    {
        "name": "create_run",
        "description": "触发一次 Agent 执行。当用户要求实现、修复、重构、测试代码时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "给 Agent 的完整任务描述。包含足够的上下文让 Agent 独立完成。"
                },
                "agent": {
                    "type": "string",
                    "enum": ["claude-code", "codex"],
                    "description": "选择 Agent。claude-code 适合大多数任务。codex 适合需要 AGENTS.md 的场景。"
                }
            },
            "required": ["task", "agent"]
        }
    },
    {
        "name": "record_memory",
        "description": "记录用户的偏好、决策、事实或教训。当用户明确表达偏好、做出技术决策、纠正 AI 错误、或陈述项目事实时调用。不要记录临时任务细节或情绪表达。",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["preference", "decision", "fact", "learning"],
                },
                "content": {
                    "type": "string",
                    "description": "记忆内容，简洁明确"
                },
                "rationale": {
                    "type": "string",
                    "description": "原因（为什么这么做/这么选），可选"
                }
            },
            "required": ["category", "content"]
        }
    },
    {
        "name": "create_watcher",
        "description": "创建自动化监视器。当用户要求 KAM 持续监控某个数据源时调用。",
        "input_schema": {
            "type": "object",
            "properties": {
                "name":          {"type": "string"},
                "source_type":   {"type": "string", "enum": ["github_pr", "azure_devops", "ci_pipeline", "repo_scan"]},
                "config":        {"type": "object", "description": "源特定配置"},
                "schedule_type": {"type": "string", "enum": ["interval", "cron"]},
                "schedule_value": {"type": "string", "description": "如 '15m', '1h', '0 9 * * *'"}
            },
            "required": ["name", "source_type", "config", "schedule_type", "schedule_value"]
        }
    }
]


# ─── System Prompt ─────────────────────────────────────────────
SYSTEM_PROMPT_TEMPLATE = """\
You are KAM, an AI development assistant that acts as an external brain.
You remember the user's preferences and past decisions.
You can execute code tasks by calling create_run.
You can set up automated watchers by calling create_watcher.
You automatically record important preferences and decisions using record_memory.

## Current project
{project_info}

## Your memory
{memory_block}

## Recent context
{recent_context}

## Guidelines
- Reply concisely. 1-3 sentences for simple questions, longer for complex ones.
- When the user asks to implement/fix/refactor something, call create_run.
- When the user expresses a preference ("always use X", "never do Y"), call record_memory.
- When the user mentions they want to monitor something, call create_watcher.
- Refer to your memories naturally: "I remember you prefer vitest over jest."
- After a Run completes, you'll receive the result. Summarize it for the user.
- For PR review comments, triage each one: needs user input vs AI can fix.
"""


async def route_message(
    *,
    thread_id: str,
    message_content: str,
    project_id: str | None,
    db,  # AsyncSession
) -> AsyncGenerator[dict, None]:
    """
    处理一条用户消息。生成器 yield 事件：
    - {"type": "text_delta", "delta": "..."} — 流式文字
    - {"type": "text_done", "content": "..."} — 完整回复
    - {"type": "tool_result", "tool": "create_run", "result": {...}} — tool 执行结果
    """
    # 1. 组装 context
    assembler = ContextAssembler(db)
    context = await assembler.assemble(thread_id=thread_id, project_id=project_id)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        project_info=context["project_info"],
        memory_block=context["memory_block"],
        recent_context=context["recent_context"],
    )

    # 2. 构建消息历史
    messages = context["conversation_messages"]
    messages.append({"role": "user", "content": message_content})

    # 3. 调用 Anthropic API（streaming）
    full_text = ""
    async with client.messages.stream(
        model=settings.chat_model,
        system=system_prompt,
        messages=messages,
        tools=TOOLS,
        max_tokens=2048,
    ) as stream:
        async for text in stream.text_stream:
            full_text += text
            yield {"type": "text_delta", "delta": text}

        # 4. 获取完整消息，处理 tool calls
        response = await stream.get_final_message()

    yield {"type": "text_done", "content": full_text}

    # 5. 处理 tool calls
    for block in response.content:
        if block.type == "tool_use":
            result = await _handle_tool(
                tool_name=block.name,
                tool_input=block.input,
                thread_id=thread_id,
                project_id=project_id,
                db=db,
            )
            yield {"type": "tool_result", "tool": block.name, "result": result}


async def _handle_tool(*, tool_name, tool_input, thread_id, project_id, db):
    if tool_name == "create_run":
        from services.run_engine import RunEngine
        engine = RunEngine(db, event_bus)
        run = await engine.create_run(
            thread_id=thread_id,
            agent=tool_input["agent"],
            task=tool_input["task"],
        )
        # 异步启动执行（不阻塞回复）
        asyncio.create_task(engine.execute_run(run.id))
        return {"run_id": run.id, "status": "pending", "task": tool_input["task"]}

    elif tool_name == "record_memory":
        from services.memory import MemoryService
        mem_svc = MemoryService(db)
        memory = await mem_svc.record(
            project_id=project_id,
            category=tool_input["category"],
            content=tool_input["content"],
            rationale=tool_input.get("rationale"),
            source_thread_id=thread_id,
        )
        return {"memory_id": memory.id, "category": memory.category}

    elif tool_name == "create_watcher":
        from services.watcher import WatcherEngine
        watcher_engine = WatcherEngine(db, event_bus)
        watcher = await watcher_engine.create_watcher(
            project_id=project_id,
            **tool_input,
        )
        return {"watcher_id": watcher.id, "name": watcher.name}
```


### 6.2 ContextAssembler — 组装 LLM 上下文

```python
# backend/services/context.py
"""
组装对话 AI 的完整上下文。控制 token 预算，确保不超限。

预算分配（总 8000 tokens）：
- project_info:       ~200 tokens（项目名、repo 路径）
- memory_block:       ~2000 tokens（始终注入偏好 + 按需检索事实）
- recent_context:     ~800 tokens（最近 Run 状态、Watcher 事件）
- conversation_messages: ~5000 tokens（对话历史，超出后压缩早期消息）
"""
import tiktoken
from services.memory import MemoryService

enc = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(enc.encode(text))

class ContextAssembler:
    def __init__(self, db):
        self.db = db

    async def assemble(self, *, thread_id: str, project_id: str | None) -> dict:
        # 1. 项目信息
        project_info = await self._build_project_info(project_id)

        # 2. 记忆（两阶段检索）
        mem_svc = MemoryService(self.db)
        memory_block = await mem_svc.build_context_block(project_id)

        # 3. 最近上下文（Runs + Watcher events）
        recent_context = await self._build_recent_context(thread_id)

        # 4. 对话历史（带压缩）
        messages = await self._build_conversation(thread_id)

        return {
            "project_info": project_info,
            "memory_block": memory_block,
            "recent_context": recent_context,
            "conversation_messages": messages,
        }

    async def _build_project_info(self, project_id: str | None) -> str:
        if not project_id:
            return "No project selected."
        project = await self.db.get(Project, project_id)
        if not project:
            return "No project selected."
        parts = [f"Project: {project.title}"]
        if project.repo_path:
            parts.append(f"Repo: {project.repo_path}")
        return "\n".join(parts)

    async def _build_recent_context(self, thread_id: str) -> str:
        """最近 3 个 Run 的状态摘要"""
        from sqlalchemy import select
        stmt = (
            select(Run)
            .where(Run.thread_id == thread_id)
            .order_by(Run.created_at.desc())
            .limit(3)
        )
        result = await self.db.execute(stmt)
        runs = result.scalars().all()
        if not runs:
            return "No recent runs."
        lines = []
        for r in runs:
            summary = r.result_summary or r.task[:100]
            lines.append(f"- Run [{r.status}]: {summary}")
        return "\n".join(lines)

    async def _build_conversation(self, thread_id: str) -> list[dict]:
        """
        构建对话历史。超过 20 条时压缩早期消息。
        返回 Anthropic messages 格式。
        """
        from sqlalchemy import select
        stmt = (
            select(Message)
            .where(Message.thread_id == thread_id)
            .order_by(Message.created_at)
        )
        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        api_messages = []
        for m in messages:
            if m.role in ("user", "assistant"):
                api_messages.append({"role": m.role, "content": m.content})

        # 压缩：保留最近 10 条，更早的压缩为摘要
        if len(api_messages) > 20:
            early = api_messages[:-10]
            recent = api_messages[-10:]
            early_text = "\n".join(f"[{m['role']}] {m['content'][:200]}" for m in early)
            summary = f"[Earlier conversation summary: {len(early)} messages]\n{early_text[:1000]}"
            api_messages = [{"role": "user", "content": summary}] + recent

        return api_messages
```


### 6.3 MemoryService — 记忆系统

```python
# backend/services/memory.py
"""
四类记忆：preference, decision, fact, learning
两阶段检索：始终注入偏好 + 按需检索事实
时间衰减：被引用加分，不用减分
矛盾处理：新记忆覆盖旧记忆时标记 superseded_by
"""
from sqlalchemy import select, and_, or_
from models import Memory
from config import settings

class MemoryService:
    def __init__(self, db):
        self.db = db

    # ─── 写入 ──────────────────────────────────────────────────
    async def record(
        self,
        *,
        project_id: str | None,
        category: str,
        content: str,
        rationale: str | None = None,
        source_thread_id: str | None = None,
    ) -> Memory:
        # 矛盾检测：查找同 project、同 category 的相似记忆
        existing = await self._find_contradicting(project_id, category, content)
        if existing:
            existing.superseded_by = "pending"  # 将被新记忆替代

        memory = Memory(
            project_id=project_id,
            scope="project" if project_id else "global",
            category=category,
            content=content,
            rationale=rationale,
            source_thread_id=source_thread_id,
        )
        self.db.add(memory)

        if existing:
            existing.superseded_by = memory.id

        await self.db.commit()
        return memory

    # ─── 检索：构建 context block ──────────────────────────────
    async def build_context_block(self, project_id: str | None) -> str:
        """
        两阶段检索，返回格式化的记忆文本。

        Stage A（始终注入）：所有 preferences + active decisions
        Stage B（按需检索）：relevance_score 最高的 facts + learnings
        """
        parts = []

        # Stage A: preferences + decisions（始终注入）
        always = await self._fetch_active(project_id, ["preference", "decision"])
        if always:
            parts.append("### Preferences & decisions")
            for m in always:
                line = f"- [{m.category}] {m.content}"
                if m.rationale:
                    line += f" (reason: {m.rationale})"
                parts.append(line)

        # Stage B: facts + learnings（按 relevance 排序取 top 5）
        relevant = await self._fetch_relevant(project_id, ["fact", "learning"], limit=5)
        if relevant:
            parts.append("### Relevant context")
            for m in relevant:
                parts.append(f"- [{m.category}] {m.content}")

        return "\n".join(parts) if parts else "No memories yet."

    # ─── 衰减 ──────────────────────────────────────────────────
    async def decay_all(self):
        """每日运行。降低未被引用的记忆分数。"""
        stmt = select(Memory).where(Memory.superseded_by.is_(None))
        result = await self.db.execute(stmt)
        for m in result.scalars().all():
            m.relevance_score = max(0.01, m.relevance_score - 0.05)
        await self.db.commit()

    async def boost(self, memory_id: str):
        """记忆被引用时调用，加分。"""
        memory = await self.db.get(Memory, memory_id)
        if memory:
            memory.relevance_score = min(5.0, memory.relevance_score + 0.2)
            memory.last_accessed_at = now()
            await self.db.commit()

    # ─── 内部方法 ──────────────────────────────────────────────
    async def _fetch_active(self, project_id, categories) -> list[Memory]:
        conditions = [
            Memory.category.in_(categories),
            Memory.superseded_by.is_(None),
        ]
        if project_id:
            conditions.append(
                or_(Memory.project_id == project_id, Memory.scope == "global")
            )
        stmt = select(Memory).where(and_(*conditions)).order_by(Memory.created_at)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _fetch_relevant(self, project_id, categories, limit=5) -> list[Memory]:
        conditions = [
            Memory.category.in_(categories),
            Memory.superseded_by.is_(None),
            Memory.relevance_score > 0.1,
        ]
        if project_id:
            conditions.append(
                or_(Memory.project_id == project_id, Memory.scope == "global")
            )
        stmt = (
            select(Memory)
            .where(and_(*conditions))
            .order_by(Memory.relevance_score.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _find_contradicting(self, project_id, category, content) -> Memory | None:
        """简单的关键词匹配找矛盾。未来可以用 embedding 相似度。"""
        # 简化实现：同 project、同 category 的记忆中，取内容最相似的
        existing = await self._fetch_active(project_id, [category])
        keywords = set(content.lower().split())
        best_match = None
        best_overlap = 0
        for m in existing:
            m_keywords = set(m.content.lower().split())
            overlap = len(keywords & m_keywords) / max(len(keywords | m_keywords), 1)
            if overlap > 0.5 and overlap > best_overlap:
                best_match = m
                best_overlap = overlap
        return best_match
```


### 6.4 RunEngine — Agent 执行

```python
# backend/services/run_engine.py
"""
执行 Claude Code / Codex CLI。

流程：
1. 创建 worktree（隔离执行环境）
2. 注入 context（记忆 + 任务描述）到 prompt
3. Async spawn CLI 子进程
4. 逐行读 stdout（stream-json），通过 EventBus 推送进度
5. 完成后触发 DigestService 生成摘要
6. 用户 adopt 时 merge worktree 回主分支
"""
import asyncio
import json
import time
from pathlib import Path
from git import Repo
from models import Run, Project
from events import EventBus
from config import settings

class RunEngine:
    def __init__(self, db, event_bus: EventBus):
        self.db = db
        self.bus = event_bus

    async def create_run(self, *, thread_id: str, agent: str, task: str) -> Run:
        run = Run(thread_id=thread_id, agent=agent, task=task, status="pending")
        self.db.add(run)
        await self.db.commit()
        return run

    async def execute_run(self, run_id: str):
        """在后台 asyncio task 里执行。"""
        from db import async_session
        async with async_session() as db:
            run = await db.get(Run, run_id)
            if not run:
                return

            thread = await db.get(Thread, run.thread_id)  # noqa
            project = await db.get(Project, thread.project_id) if thread else None
            repo_path = project.repo_path if project else None

            # 更新状态
            run.status = "running"
            await db.commit()
            self.bus.publish(f"thread:{run.thread_id}", {
                "type": "run-status", "run_id": run_id, "status": "running"
            })

            start = time.monotonic()
            try:
                # 1. 准备 worktree（如果有 repo）
                worktree_path = None
                if repo_path:
                    worktree_path = await self._setup_worktree(repo_path, run_id)
                    run.worktree_path = str(worktree_path)

                execution_cwd = worktree_path or Path.cwd()

                # 2. 构建命令
                command = self._build_command(
                    agent=run.agent,
                    task=run.task,
                    cwd=str(execution_cwd),
                )

                # 3. Async 执行 + 实时推送
                stdout_lines = []
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(execution_cwd),
                )

                async for line_bytes in proc.stdout:
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    stdout_lines.append(line)

                    # 尝试解析 stream-json
                    progress = self._parse_stream_json(line)
                    if progress:
                        self.bus.publish(f"thread:{run.thread_id}", {
                            "type": "run-progress",
                            "run_id": run_id,
                            "detail": progress.get("description", line[:200]),
                        })

                await proc.wait()
                duration = int((time.monotonic() - start) * 1000)

                # 4. 更新结果
                run.status = "passed" if proc.returncode == 0 else "failed"
                run.duration_ms = duration
                run.raw_output = "\n".join(stdout_lines[-50:])  # 保留最后 50 行

                if worktree_path:
                    run.changed_files = self._get_changed_files(worktree_path)

                await db.commit()

                # 5. 触发 AI 摘要
                from services.digest import DigestService
                digest = DigestService(db)
                summary = await digest.summarize_run(run)
                run.result_summary = summary
                await db.commit()

                # 6. 推送完成事件
                self.bus.publish(f"thread:{run.thread_id}", {
                    "type": "run-complete",
                    "run_id": run_id,
                    "status": run.status,
                    "summary": summary,
                    "changed_files": run.changed_files,
                    "duration_ms": duration,
                })
                # 也推到 home feed
                self.bus.publish("home", {
                    "type": "run-complete",
                    "run_id": run_id,
                    "thread_id": run.thread_id,
                    "status": run.status,
                    "summary": summary,
                })

            except Exception as e:
                run.status = "failed"
                run.result_summary = f"Execution error: {str(e)}"
                run.duration_ms = int((time.monotonic() - start) * 1000)
                await db.commit()
                self.bus.publish(f"thread:{run.thread_id}", {
                    "type": "run-complete",
                    "run_id": run_id,
                    "status": "failed",
                    "summary": run.result_summary,
                })

    def _build_command(self, *, agent: str, task: str, cwd: str) -> list[str]:
        if agent == "claude-code":
            return [
                settings.claude_code_path,
                "-p",                            # prompt mode
                "--dangerously-skip-permissions", # no confirmation prompts
                "--output-format", "stream-json", # structured streaming output
                task,
            ]
        elif agent == "codex":
            return [
                settings.codex_path,
                "--approval-mode", "full-auto",
                "--quiet",
                task,
            ]
        else:
            raise ValueError(f"Unknown agent: {agent}")

    def _parse_stream_json(self, line: str) -> dict | None:
        try:
            obj = json.loads(line)
            if obj.get("type") == "assistant":
                return {"description": obj.get("message", {}).get("content", [{}])[0].get("text", "")[:200]}
            return obj
        except (json.JSONDecodeError, KeyError, IndexError):
            return None

    async def _setup_worktree(self, repo_path: str, run_id: str) -> Path:
        repo = Repo(repo_path)
        branch = f"kam/run-{run_id[:8]}"
        wt_path = Path(repo_path).parent / f".kam-worktrees/{run_id[:8]}"
        wt_path.parent.mkdir(parents=True, exist_ok=True)
        repo.git.worktree("add", str(wt_path), "-b", branch)
        return wt_path

    def _get_changed_files(self, worktree_path: Path) -> list[str]:
        try:
            repo = Repo(str(worktree_path))
            diff = repo.git.diff("HEAD~1", "--name-only")
            return diff.strip().split("\n") if diff.strip() else []
        except Exception:
            return []

    # ─── Adopt ──────────────────────────────────────────────────
    async def adopt_run(self, run_id: str) -> dict:
        run = await self.db.get(Run, run_id)
        if not run or run.status != "passed":
            return {"ok": False, "error": "Only passed runs can be adopted."}

        if not run.worktree_path:
            return {"ok": False, "error": "No worktree to merge."}

        try:
            thread = await self.db.get(Thread, run.thread_id)
            project = await self.db.get(Project, thread.project_id)
            repo = Repo(project.repo_path)

            branch = f"kam/run-{run_id[:8]}"
            repo.git.merge(branch, "--no-ff", m=f"KAM: {run.task[:100]}")
            repo.git.worktree("remove", run.worktree_path, "--force")

            run.adopted_at = now()
            await self.db.commit()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}
```


### 6.5 WatcherEngine — 自动化监控

```python
# backend/services/watcher.py
"""
定时监控外部数据源。

使用 APScheduler 管理定时任务。
每次触发：拉取数据 → diff 上次 → AI 分析 → 注入 Home feed。
"""
from apscheduler import AsyncScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from models import Watcher, WatcherEvent
from events import EventBus

class WatcherEngine:
    def __init__(self, db, event_bus: EventBus):
        self.db = db
        self.bus = event_bus
        self.scheduler: AsyncScheduler | None = None

    async def start(self, scheduler: AsyncScheduler):
        """应用启动时调用，加载所有 active watchers。"""
        self.scheduler = scheduler
        from sqlalchemy import select
        stmt = select(Watcher).where(Watcher.status == "active")
        result = await self.db.execute(stmt)
        for w in result.scalars().all():
            await self._schedule(w)

    async def create_watcher(self, *, project_id, name, source_type, config,
                              schedule_type, schedule_value) -> Watcher:
        watcher = Watcher(
            project_id=project_id,
            name=name,
            source_type=source_type,
            config=config,
            schedule_type=schedule_type,
            schedule_value=schedule_value,
        )
        self.db.add(watcher)
        await self.db.commit()
        await self._schedule(watcher)
        return watcher

    async def _schedule(self, watcher: Watcher):
        trigger = self._parse_trigger(watcher.schedule_type, watcher.schedule_value)
        await self.scheduler.add_schedule(
            self._tick,
            trigger=trigger,
            id=f"watcher:{watcher.id}",
            kwargs={"watcher_id": watcher.id},
        )

    async def _tick(self, watcher_id: str):
        """每次定时触发的执行逻辑。"""
        from db import async_session
        async with async_session() as db:
            watcher = await db.get(Watcher, watcher_id)
            if not watcher or watcher.status != "active":
                return

            # 1. 通过 adapter 拉取数据
            adapter = self._get_adapter(watcher.source_type)
            new_data = await adapter.fetch(watcher.config)

            # 2. Diff with last state
            changes = adapter.diff(watcher.last_state, new_data)
            if not changes:
                watcher.last_run_at = now()
                await db.commit()
                return

            # 3. AI 分析变更
            from services.digest import DigestService
            digest = DigestService(db)
            analysis = await digest.analyze_watcher_changes(
                watcher=watcher,
                changes=changes,
            )

            # 4. 创建事件
            event = WatcherEvent(
                watcher_id=watcher.id,
                event_type=changes.get("type", watcher.source_type),
                title=analysis["title"],
                summary=analysis["summary"],
                raw_data=changes,
                actions=analysis.get("actions"),
            )
            db.add(event)

            # 5. 更新 watcher 状态
            watcher.last_state = new_data
            watcher.last_run_at = now()
            await db.commit()

            # 6. 推送到 Home feed
            self.bus.publish("home", {
                "type": "watcher-event",
                "event_id": event.id,
                "watcher_name": watcher.name,
                "title": event.title,
                "summary": event.summary,
                "actions": event.actions,
            })

    def _get_adapter(self, source_type: str):
        from adapters import github, azure_devops, ci
        adapters = {
            "github_pr": github.GitHubPRAdapter,
            "azure_devops": azure_devops.AzureDevOpsAdapter,
            "ci_pipeline": ci.CIPipelineAdapter,
            "repo_scan": ci.RepoScanAdapter,
        }
        cls = adapters.get(source_type)
        if not cls:
            raise ValueError(f"Unknown source type: {source_type}")
        return cls()

    def _parse_trigger(self, schedule_type: str, value: str):
        if schedule_type == "interval":
            # "15m" → 15 minutes, "1h" → 1 hour
            if value.endswith("m"):
                return IntervalTrigger(minutes=int(value[:-1]))
            elif value.endswith("h"):
                return IntervalTrigger(hours=int(value[:-1]))
        elif schedule_type == "cron":
            parts = value.split()
            return CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4]
            )
        raise ValueError(f"Cannot parse schedule: {schedule_type} {value}")
```


### 6.6 DigestService — AI 摘要生成

```python
# backend/services/digest.py
"""
所有 AI 摘要在这里生成。
- Run 完成后的结果摘要
- Watcher 事件的分析
- Thread 恢复摘要（"上次做到哪了"）
- PR review comment triage

统一使用 digest_model（Sonnet），成本低、速度快。
"""
import anthropic
from config import settings

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

class DigestService:
    def __init__(self, db):
        self.db = db

    async def summarize_run(self, run) -> str:
        if run.status == "passed":
            prompt = f"""Summarize this completed coding task in 1-3 sentences for a developer.
Task: {run.task}
Changed files: {run.changed_files}
Output tail: {(run.raw_output or '')[-2000:]}
Be concise. State what was done, which files changed, and test results if any."""
        else:
            prompt = f"""Explain why this coding task failed in 1-3 sentences.
Task: {run.task}
Output tail: {(run.raw_output or '')[-2000:]}
State the failure reason and suggest a next step."""

        return await self._call(prompt)

    async def analyze_watcher_changes(self, *, watcher, changes) -> dict:
        prompt = f"""Analyze these changes detected by a monitoring watcher.

Watcher: {watcher.name} ({watcher.source_type})
Changes: {json.dumps(changes, default=str)[:3000]}

Return a JSON object with:
- "title": short title (under 60 chars)
- "summary": 2-3 sentence analysis
- "actions": list of suggested actions, each with "label" and "action_type" (one of: "start_thread", "run", "dismiss")

Respond ONLY with the JSON object."""

        raw = await self._call(prompt)
        try:
            return json.loads(raw.strip().strip("```json").strip("```"))
        except json.JSONDecodeError:
            return {"title": "New event", "summary": raw, "actions": []}

    async def restore_thread_summary(self, thread_id: str) -> str:
        """用户切回旧 thread 时，生成"上次做到哪了"的摘要。"""
        from sqlalchemy import select
        from models import Message, Run

        # 最近 5 条消息
        stmt = select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at.desc()).limit(5)
        result = await self.db.execute(stmt)
        messages = list(reversed(result.scalars().all()))

        # 最近 1 个 run
        stmt = select(Run).where(Run.thread_id == thread_id).order_by(Run.created_at.desc()).limit(1)
        result = await self.db.execute(stmt)
        last_run = result.scalar_one_or_none()

        history = "\n".join(f"[{m.role}] {m.content[:200]}" for m in messages)
        run_info = f"Last run: {last_run.status} — {last_run.result_summary}" if last_run else "No runs."

        prompt = f"""You're resuming a conversation. Summarize what was being worked on in 1-3 sentences.

Recent messages:
{history}

{run_info}

Start with "Last time, you were..." """

        return await self._call(prompt)

    async def triage_pr_comments(self, *, comments: list[dict], code_context: str, memory_block: str) -> list[dict]:
        """PR review comment 分类：needs_input vs ai_can_fix。"""
        prompt = f"""Triage these PR review comments. For each, determine if:
1. "needs_input" — subjective/design question, needs the developer's judgment
2. "ai_can_fix" — objective code issue, you can generate a fix

Project context from memory:
{memory_block}

Relevant code:
{code_context[:3000]}

Comments:
{json.dumps(comments, indent=2)[:3000]}

Return a JSON array. Each item has:
- "comment_id": original ID
- "triage": "needs_input" or "ai_can_fix"
- "draft_reply": your suggested reply text
- "fix_description": (only for ai_can_fix) what the fix should do

Respond ONLY with the JSON array."""

        raw = await self._call(prompt)
        try:
            return json.loads(raw.strip().strip("```json").strip("```"))
        except json.JSONDecodeError:
            return []

    async def _call(self, prompt: str) -> str:
        response = await client.messages.create(
            model=settings.digest_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
```


### 6.7 Source Adapters（示例：GitHub）

```python
# backend/adapters/github.py
"""
GitHub PR adapter。
- fetch: 拉取指定 repo 的 PR review comments
- diff: 对比上次状态，找出新评论
"""
from ghapi.all import GhApi
from config import settings

class GitHubPRAdapter:
    def __init__(self):
        self.api = GhApi(token=settings.github_token) if settings.github_token else None

    async def fetch(self, config: dict) -> dict:
        """拉取 PR 的 review comments 和状态。"""
        owner, repo = config["repo"].split("/")
        prs = list(self.api.pulls.list(
            owner=owner, repo=repo, state="open",
            sort="updated", direction="desc", per_page=10,
        ))

        result = {"prs": []}
        for pr in prs:
            comments = list(self.api.pulls.list_review_comments(
                owner=owner, repo=repo, pull_number=pr.number
            ))
            result["prs"].append({
                "number": pr.number,
                "title": pr.title,
                "author": pr.user.login,
                "comments": [
                    {
                        "id": c.id,
                        "author": c.user.login,
                        "body": c.body,
                        "path": c.path,
                        "line": c.line,
                        "created_at": c.created_at,
                    }
                    for c in comments
                ]
            })
        return result

    def diff(self, last_state: dict | None, new_state: dict) -> dict | None:
        """找出新增的 comments。"""
        if not last_state:
            return {"type": "initial_scan", "data": new_state}

        old_ids = set()
        for pr in (last_state.get("prs") or []):
            for c in pr.get("comments", []):
                old_ids.add(c["id"])

        new_comments = []
        for pr in new_state.get("prs", []):
            for c in pr.get("comments", []):
                if c["id"] not in old_ids:
                    new_comments.append({**c, "pr_number": pr["number"], "pr_title": pr["title"]})

        if not new_comments:
            return None

        return {
            "type": "new_pr_comments",
            "comments": new_comments,
            "count": len(new_comments),
        }

    async def post_reply(self, *, repo: str, pr_number: int, comment_id: int, body: str):
        owner, repo_name = repo.split("/")
        self.api.pulls.create_reply_for_review_comment(
            owner=owner, repo=repo_name,
            pull_number=pr_number, comment_id=comment_id, body=body,
        )
```

---

## 7. API 端点

### 7.1 Thread + SSE

```python
# backend/api/threads.py
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from db import get_db
from events import event_bus
from services.router import route_message

router = APIRouter(prefix="/api/threads", tags=["threads"])

@router.post("/{thread_id}/messages")
async def send_message(thread_id: str, body: dict, db=Depends(get_db)):
    """发送消息 → 返回 SSE 流式回复。"""
    # 保存用户消息
    msg = Message(thread_id=thread_id, role="user", content=body["content"])
    db.add(msg)
    await db.commit()

    # 获取 thread 的 project_id
    thread = await db.get(Thread, thread_id)
    project_id = thread.project_id if thread else None

    async def generate():
        full_reply = ""
        async for event in route_message(
            thread_id=thread_id,
            message_content=body["content"],
            project_id=project_id,
            db=db,
        ):
            if event["type"] == "text_delta":
                yield {"event": "text_delta", "data": json.dumps({"delta": event["delta"]})}
                full_reply += event["delta"]
            elif event["type"] == "text_done":
                # 保存 AI 回复
                reply = Message(thread_id=thread_id, role="assistant", content=event["content"])
                db.add(reply)
                await db.commit()
                yield {"event": "text_done", "data": json.dumps({"content": event["content"]})}
            elif event["type"] == "tool_result":
                yield {"event": "tool_result", "data": json.dumps(event)}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())


@router.get("/{thread_id}/events")
async def stream_events(thread_id: str):
    """实时事件流：Run 进度、完成通知等。"""
    queue = event_bus.subscribe(f"thread:{thread_id}")

    async def generate():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": event["type"], "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            event_bus.unsubscribe(f"thread:{thread_id}", queue)

    return EventSourceResponse(generate())


@router.get("")
async def list_threads(db=Depends(get_db)):
    """列出所有 threads，按 project 分组，按 updated_at 排序。"""
    stmt = (
        select(Thread)
        .options(selectinload(Thread.project))
        .order_by(Thread.updated_at.desc())
    )
    result = await db.execute(stmt)
    threads = result.scalars().all()

    # 按 project 分组
    grouped = {}
    for t in threads:
        proj_name = t.project.title if t.project else "No project"
        grouped.setdefault(proj_name, []).append({
            "id": t.id,
            "title": t.title,
            "updated_at": t.updated_at.isoformat(),
            "has_active_run": any(r.status in ("pending", "running") for r in t.runs),
            "latest_run_status": t.runs[-1].status if t.runs else None,
        })
    return grouped
```


### 7.2 Home Feed

```python
# backend/api/home.py
from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/home", tags=["home"])

@router.get("/feed")
async def get_feed(db=Depends(get_db)):
    """
    Home feed 聚合。三层：
    1. 需要关注：passed 未 adopt 的 Run + failed Run + pending WatcherEvent
    2. 运行中：running Run
    3. 最近历史：最近 5 个已完成项
    """
    # 需要关注的 Runs
    attention_runs = await db.execute(
        select(Run).where(
            or_(
                and_(Run.status == "passed", Run.adopted_at.is_(None)),
                Run.status == "failed",
            )
        ).order_by(Run.created_at.desc()).limit(10)
    )

    # 需要关注的 Watcher events
    attention_events = await db.execute(
        select(WatcherEvent)
        .where(WatcherEvent.status == "pending")
        .order_by(WatcherEvent.created_at.desc())
        .limit(10)
    )

    # 运行中
    running = await db.execute(
        select(Run).where(Run.status == "running")
    )

    # 最近完成
    recent = await db.execute(
        select(Run).where(Run.status.in_(["passed", "failed"]))
        .order_by(Run.created_at.desc()).limit(5)
    )

    return {
        "needs_attention": [
            *[_run_to_feed_item(r) for r in attention_runs.scalars()],
            *[_event_to_feed_item(e) for e in attention_events.scalars()],
        ],
        "running": [_run_to_feed_item(r) for r in running.scalars()],
        "recent": [_run_to_feed_item(r) for r in recent.scalars()],
    }


@router.get("/events")
async def stream_home_events():
    """Home feed 实时更新。"""
    queue = event_bus.subscribe("home")

    async def generate():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield {"event": event["type"], "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"comment": "keepalive"}
        finally:
            event_bus.unsubscribe("home", queue)

    return EventSourceResponse(generate())
```


### 7.3 Runs

```python
# backend/api/runs.py
router = APIRouter(prefix="/api/runs", tags=["runs"])

@router.post("/{run_id}/adopt")
async def adopt_run(run_id: str, db=Depends(get_db)):
    engine = RunEngine(db, event_bus)
    result = await engine.adopt_run(run_id)
    return result

@router.get("/{run_id}")
async def get_run(run_id: str, db=Depends(get_db)):
    run = await db.get(Run, run_id)
    if not run:
        raise HTTPException(404)
    return run
```


### 7.4 Watchers

```python
# backend/api/watchers.py
router = APIRouter(prefix="/api/watchers", tags=["watchers"])

@router.get("")
async def list_watchers(db=Depends(get_db)):
    result = await db.execute(select(Watcher).order_by(Watcher.created_at.desc()))
    return [w for w in result.scalars()]

@router.post("/{watcher_id}/pause")
async def pause_watcher(watcher_id: str, db=Depends(get_db)):
    watcher = await db.get(Watcher, watcher_id)
    watcher.status = "paused"
    await db.commit()
    # APScheduler 暂停
    await watcher_engine.scheduler.pause_schedule(f"watcher:{watcher_id}")
    return {"ok": True}

@router.post("/{watcher_id}/resume")
async def resume_watcher(watcher_id: str, db=Depends(get_db)):
    watcher = await db.get(Watcher, watcher_id)
    watcher.status = "active"
    await db.commit()
    await watcher_engine.scheduler.resume_schedule(f"watcher:{watcher_id}")
    return {"ok": True}
```

---

## 8. 应用入口

```python
# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler import AsyncScheduler
from db import engine, async_session
from models import Base
from events import event_bus
from services.watcher import WatcherEngine
from services.memory import MemoryService

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ─── 启动 ───────────────────────────────────────────
    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 启动 scheduler
    scheduler = AsyncScheduler()
    await scheduler.start_in_background()

    # 加载 watchers
    async with async_session() as db:
        watcher_engine = WatcherEngine(db, event_bus)
        await watcher_engine.start(scheduler)
        app.state.watcher_engine = watcher_engine

    # 每日记忆衰减任务
    from apscheduler.triggers.cron import CronTrigger
    async def daily_memory_decay():
        async with async_session() as db:
            await MemoryService(db).decay_all()
    await scheduler.add_schedule(daily_memory_decay, CronTrigger(hour=3), id="memory-decay")

    yield

    # ─── 关闭 ───────────────────────────────────────────
    await scheduler.stop()

app = FastAPI(title="KAM", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from api import threads, runs, watchers, home, memory_api
app.include_router(threads.router)
app.include_router(runs.router)
app.include_router(watchers.router)
app.include_router(home.router)
app.include_router(memory_api.router)
```

---

## 9. 前端核心 Hooks

### 9.1 useSSE — 订阅事件流

```typescript
// frontend/src/hooks/useSSE.ts
import { useEffect, useRef, useCallback, useState } from 'react';

export function useSSE(url: string, onEvent: (event: string, data: any) => void) {
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource(url);
    sourceRef.current = es;

    es.addEventListener('text_delta', (e) => onEvent('text_delta', JSON.parse(e.data)));
    es.addEventListener('text_done', (e) => onEvent('text_done', JSON.parse(e.data)));
    es.addEventListener('tool_result', (e) => onEvent('tool_result', JSON.parse(e.data)));
    es.addEventListener('run-status', (e) => onEvent('run-status', JSON.parse(e.data)));
    es.addEventListener('run-progress', (e) => onEvent('run-progress', JSON.parse(e.data)));
    es.addEventListener('run-complete', (e) => onEvent('run-complete', JSON.parse(e.data)));
    es.addEventListener('watcher-event', (e) => onEvent('watcher-event', JSON.parse(e.data)));
    es.addEventListener('done', () => es.close());

    return () => es.close();
  }, [url]);
}
```

### 9.2 useSendMessage — 发送消息 + 流式回复

```typescript
// frontend/src/hooks/useSendMessage.ts
export function useSendMessage(threadId: string) {
  const [streaming, setStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState('');

  const send = useCallback(async (content: string) => {
    setStreaming(true);
    setStreamedText('');

    const response = await fetch(`/api/threads/${threadId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // 解析 SSE 行
      const lines = buffer.split('\n');
      buffer = lines.pop()!;
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          if (data.delta) {
            setStreamedText(prev => prev + data.delta);
          }
        }
      }
    }
    setStreaming(false);
  }, [threadId]);

  return { send, streaming, streamedText };
}
```

---

## 10. 启动命令

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 前端
cd frontend
npm install
npm run dev
```

第一次启动会自动创建 `kam.db`（SQLite）和所有表。

---

## 11. 实现顺序

```
Week 1:  models.py + db.py + main.py + 基础 CRUD API
         → 能创建 project/thread/message，有空壳 UI

Week 2:  ConversationRouter + ContextAssembler
         → 用户打字，AI 真实流式回复

Week 3:  RunEngine（async subprocess + stream-json）
         → AI 调 create_run tool，Claude Code 执行，实时进度

Week 4:  DigestService + adopt_run
         → Run 完成后 AI 摘要，点按钮合并代码

Week 5:  MemoryService（记录 + 检索 + 衰减）
         → AI 自动记住偏好和决策，对话质量显著提升

Week 6:  EventBus + SSE（sse-starlette）
         → 实时推送 Run 进度、Home feed 更新

Week 7:  WatcherEngine + APScheduler + GitHub adapter
         → 自动监控 PR 评论，AI 分析后推送

Week 8:  前端完整重构（按组件结构）
         → 三栏布局、Home feed、Run card、Memory panel
```

---

*设计完成于 2026-03-27。基于之前全部讨论的 UI 原型 + 技术分析。*
