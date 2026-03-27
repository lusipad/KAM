# KAM v2 实现路线图

> 本文档基于完整的架构分析，作为 AI Agent 后续开发的执行指南。
> 目标：把 KAM 从"能跑但体验假"变成真正的"外置大脑 + AI 控制台"。

---

## 一、当前状态总结

### 已完成（不需要改动）

| 模块 | 状态 | 位置 |
|------|------|------|
| 数据模型 | ✅ 完整 | `backend/app/models/` |
| REST API | ✅ 完整 | `backend/app/api/` |
| ConversationRouter（骨架） | ✅ 有但需升级 | `backend/app/services/conversation_router.py` |
| ContextAssembler | ✅ 有但需优化 | `backend/app/services/context_assembler.py` |
| RunEngine（执行循环） | ✅ 完整 | `backend/app/services/run_engine.py` |
| MemoryService | ✅ 完整 | `backend/app/services/memory_service.py` |
| SSE 框架 | ✅ 有但是轮询伪装 | `backend/app/api/threads.py` |
| Bootstrap 端点 | ✅ 完整 | `POST /api/v2/bootstrap/message` |

### 核心缺陷（本路线图要解决的）

1. **AI 回复是模板字符串**：`_build_reply()` 拼接固定文字，不是真正的 LLM 调用
2. **Run 结果无人消化**：执行完成后没有 AI 读取 artifacts 生成 thread 消息
3. **采纳变更没有实现**：Worktree 执行完的代码无法合入原始仓库
4. **SSE 是轮询**：`threads/events` 每秒查一次数据库，不是真推送
5. **Claude Code adapter 错误**：`--permission-mode bypassPermissions` 已废弃，且缺上下文注入
6. **没有 Skill 系统**：无法定义可复用的命名工作流
7. **前端是单文件巨组件**：`WorkspaceView.tsx` 33K+ token，无法维护

---

## 二、技术选型决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 对话 AI SDK | **Anthropic SDK**（`anthropic` Python 包） | 替换现有 OpenAI 路由器，支持真实 streaming |
| 对话 AI 模型 | `claude-opus-4-5` 或 `claude-sonnet-4-6` | 对话质量 + 成本平衡，可配置 |
| Run 实时进度 | **`--output-format stream-json`**（Claude Code 原生） | 不需要 MCP，直接解析 CLI 的结构化 JSON 输出 |
| 事件推送 | **asyncio.Queue**（in-process event bus） | 替换当前的数据库轮询，单机够用 |
| 采纳变更 | **git worktree merge** | worktree 分支 → 合入项目主分支 |
| Skill 存储 | **数据库 `skills` 表** + 自动发现 `.claude/skills/` | 统一管理，Claude Code native 文件作为来源之一 |

---

## 三、实现阶段

### Phase 1：真实对话 AI（最高优先级）

**目标**：用户发消息后看到 AI 真正理解项目状态的流式回复，而不是模板文字。

**影响文件**：
- `backend/app/services/conversation_router.py`（主要改动）
- `backend/app/api/threads.py`（SSE streaming 对接）
- `backend/app/core/config.py`（新增 Anthropic 配置）

#### 任务 1.1：增加 Anthropic SDK 配置

在 `config.py` 新增：

```python
ANTHROPIC_API_KEY: str = ""
ANTHROPIC_MODEL: str = "claude-opus-4-5"
# 保留 OPENAI 配置用于 Codex 路由
```

#### 任务 1.2：重构 ConversationRouter

当前 `_build_reply()` 是模板拼接，`_route_with_llm()` 只做路由判断。

**目标架构**：一次 LLM 调用同时完成"路由判断 + 生成回复 + 记忆提取"：

```python
async def route_async(self, *, thread_id, message_id, user_message, ...) -> AsyncGenerator:
    context = self.context_assembler.assemble(thread_id) or {}

    # 单次 LLM 调用：streaming 回复 + tool_use 路由
    async with anthropic_client.messages.stream(
        model=settings.ANTHROPIC_MODEL,
        system=self._build_system_prompt(context),
        messages=self._build_conversation_messages(context, user_message),
        tools=[
            self._create_run_tool(),      # 触发 Agent 执行
            self._record_memory_tool(),   # 记录偏好/决策
        ],
        max_tokens=2048,
    ) as stream:
        # 1. 流式文字 → 逐 token 推给前端
        async for text in stream.text_stream:
            yield {"type": "text_delta", "delta": text}

        # 2. tool_use 结果 → 创建 Run / 记录记忆
        message = await stream.get_final_message()
        for block in message.content:
            if block.type == "tool_use":
                yield await self._handle_tool_call(block, thread_id, message_id, context)
```

**System Prompt 设计原则**：
- 告知 AI 当前项目状态（thread 历史、上次 run 摘要）
- 注入 memory（偏好、决策、learnings）
- 明确指示：何时用 `create_run` tool（用户要求执行/实现/修复时）
- 明确指示：何时用 `record_memory` tool（用户明确表达偏好/做出决策时）

**`create_run` tool 的输入参数**：
```json
{
  "task_description": "给 Agent 的完整任务描述（AI 生成，而非模板）",
  "agent": "claude-code | codex | custom",
  "rationale": "为什么这样做（简短说明，注入 run prompt 帮助 Agent 理解背景）"
}
```

#### 任务 1.3：更新 SSE 端点支持流式路由结果

在 `threads.py` 的 `_message_streaming_response` 里，调用 `route_async` 而非同步 `route`，把每个 yield 的事件直接转发给前端。

事件类型：
- `assistant-reply-delta`：流式文字片段
- `assistant-reply-complete`：完整回复
- `runs-created`：Run 已创建（含 run 详情）
- `memory-recorded`：记忆已记录
- `done`：本轮完成

#### 任务 1.4：Thread 切换时的恢复摘要

当用户切换到已有 Thread（`GET /api/v2/threads/{id}`），如果 Thread 有历史消息且最后一条不是今天，触发一次轻量 LLM 调用：

```python
async def generate_restore_summary(self, thread_id: str) -> str:
    """生成 '上次做到哪了' 的恢复摘要"""
    context = self.context_assembler.assemble(thread_id)
    # 输入：thread 历史 + 最近 run 结果
    # 输出：1-3 句话的状态摘要
    # 注入为 assistant 消息，显示在对话顶部
```

---

### Phase 2：Run 结果 AI 消化

**目标**：Run 完成/失败后，AI 自动读取 artifacts，生成用户可见的结果摘要注入 thread。

**影响文件**：
- `backend/app/services/run_engine.py`（Run 完成后触发）
- `backend/app/services/conversation_router.py`（新增 digest 方法）

#### 任务 2.1：RunEngine 完成后触发 digest

在 `_execute_run` 的 `run.status = "passed"` 和 `run.status = "failed"` 两处之后，异步触发：

```python
# run_engine.py，Run 完成后
self._schedule_run_digest(db, run.id, run.thread_id, run.status)
```

`_schedule_run_digest` 在新线程里执行（不阻塞当前执行循环）：

```python
def _do_run_digest(self, run_id: str, thread_id: str, status: str):
    """读取 run artifacts，调用 LLM 生成摘要，注入 thread"""
    db = SessionLocal()
    try:
        summary = self._artifact_content(db, run_id, "summary")
        check_results = self._artifact_content(db, run_id, "check_result")
        changes = self._artifact_content(db, run_id, "changes")
        run = db.query(Run).filter(Run.id == run_id).first()

        digest = self._call_digest_llm(
            status=status,
            agent=run.agent,
            rounds=run.round,
            duration_ms=run.duration_ms,
            summary=summary,
            check_results=check_results,
            changes=changes,
        )

        thread_service = ThreadService(db)
        thread_service.create_message(thread_id, {
            "role": "assistant",
            "content": digest,
            "metadata": {
                "generatedBy": "run-digest",
                "runId": run_id,
                "runStatus": status,
            }
        })
    finally:
        db.close()
```

**Digest LLM Prompt 设计**：
- Passed：说明完成了什么、改了哪些文件、测试结果，1-4 句话
- Failed：说明失败原因、最后一轮错误，建议下一步，1-3 句话
- 保持简洁，不要重复 raw 数据，给出人能直接理解的结论

---

### Phase 3：采纳变更（Git 闭环）

**目标**：用户点"采纳变更"后，worktree 里的代码真正合入项目仓库。

**影响文件**：
- `backend/app/services/run_engine.py`（新增 adopt 方法）
- `backend/app/api/runs.py`（新增 adopt 端点）
- `backend/app/models/conversation.py`（Run 新增 `adopted_at` 字段）

#### 任务 3.1：RunEngine 实现 adopt_run

```python
def adopt_run(self, run_id: str) -> dict:
    """
    把 worktree 里的变更合入项目主分支。
    策略：
      1. 如果有 worktree → git merge worktree 分支
      2. 如果没有 worktree 但有 patch → git apply patch
      3. 都没有 → 返回错误
    """
    db = SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run or run.status != "passed":
            return {"success": False, "error": "只有 passed 的 Run 才能采纳"}

        worktree_path = (run.metadata_ or {}).get("worktree")
        if worktree_path:
            return self._adopt_via_worktree_merge(run, Path(worktree_path), db)

        # fallback: apply patch artifact
        patch_content = self._artifact_content(db, run_id, "patch")
        if patch_content:
            return self._adopt_via_patch(run, patch_content, db)

        return {"success": False, "error": "没有可采纳的变更"}
    finally:
        db.close()

def _adopt_via_worktree_merge(self, run, worktree: Path, db) -> dict:
    repo_path = self._resolve_repo_path(run.thread.project)
    # git -C {repo_path} merge --no-ff {worktree_branch}
    # 更新 run.metadata_["adopted"] = True
    # 清理 worktree
    ...
```

#### 任务 3.2：新增 adopt API 端点

```
POST /api/v2/runs/{run_id}/adopt
```

在 `runs.py` 里添加，调用 `run_engine.adopt_run(run_id)`。

#### 任务 3.3：Worktree 清理

Run 完成后（无论 passed/failed/cancelled）：
- `failed` / `cancelled`：立即清理 worktree
- `passed`：等待 adopt 后清理（或超时 24h 后自动清理）

在 RunEngine 的 finally 块里处理。

---

### Phase 4：SSE 真实事件推送

**目标**：用 in-process 事件 bus 替换数据库轮询，Run 执行中能推送细粒度进度。

**影响文件**：
- `backend/app/core/events.py`（新建：事件 bus）
- `backend/app/services/run_engine.py`（发布事件）
- `backend/app/api/threads.py`（订阅事件，替换轮询）

#### 任务 4.1：实现 in-process 事件 bus

```python
# backend/app/core/events.py
import asyncio
from collections import defaultdict
from typing import Any

class EventBus:
    def __init__(self):
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, channel: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._queues[channel].append(q)
        return q

    def unsubscribe(self, channel: str, q: asyncio.Queue):
        self._queues[channel].remove(q)

    def publish(self, channel: str, event: dict[str, Any]):
        """从同步线程（RunEngine）发布事件"""
        for q in list(self._queues.get(channel, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

event_bus = EventBus()  # 全局单例
```

#### 任务 4.2：RunEngine 发布事件

在 `_execute_run` 的每个状态变更处：

```python
from app.core.events import event_bus

# 发布到 thread 频道
event_bus.publish(f"thread:{run.thread_id}", {
    "type": "run-progress",
    "runId": run_id,
    "status": run.status,
    "round": round_number,
    "stdoutTail": _tail_text(stdout_text, 400),  # 最近几行 stdout
})
```

#### 任务 4.3：SSE 端点订阅事件 bus

```python
# threads.py
@router.get("/threads/{thread_id}/events")
async def stream_thread_events(thread_id: str, request: Request):
    queue = event_bus.subscribe(f"thread:{thread_id}")

    async def event_stream():
        try:
            # 先发送当前状态快照
            yield _encode_sse_event("snapshot", get_thread_snapshot(thread_id))

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                    yield _encode_sse_event(event["type"], event)
                    if event.get("type") == "thread-done":
                        break
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            event_bus.unsubscribe(f"thread:{thread_id}", queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream", ...)
```

#### 任务 4.4：Claude Code 实时 stdout（--output-format stream-json）

修改 `run_engine.py` 的 Claude Code 命令，解析 stream-json 格式输出并实时推送：

```python
if run.agent in {"claude", "claude-code"}:
    command = [
        executable, "-p",
        "--dangerously-skip-permissions",  # 修复：替换废弃的 bypassPermissions
        "--output-format", "stream-json",  # 启用结构化流式输出
        "--cwd", str(execution_cwd),       # 修复：显式指定工作目录
        prompt_text,
    ]
```

解析 stream-json 行，把 `assistant` 类型的事件通过 event_bus 推送到前端。

---

### Phase 5：Claude Code Adapter 修复

**目标**：修复现有的 Claude Code 执行问题，让它真正能用。

**影响文件**：`backend/app/services/run_engine.py`

#### 任务 5.1：修复权限标志

```python
# 旧（已废弃）
"--permission-mode", "bypassPermissions"

# 新
"--dangerously-skip-permissions"
```

#### 任务 5.2：注入上下文文件

Codex 会读 `context_path`，Claude Code 目前不传。改为：

```python
command = [
    executable, "-p",
    "--dangerously-skip-permissions",
    "--output-format", "stream-json",
    "--cwd", str(execution_cwd),
    # context 注入到 prompt 里（因为 claude CLI 没有 --context 参数）
    f"# Context\n\n{base_context}\n\n# Task\n\n{prompt_text}",
]
```

#### 任务 5.3：ContextAssembler Token Budget

在 `context_assembler.py` 的 `assemble()` 里加 token 估算和截断：

```python
def _estimate_tokens(self, text: str) -> int:
    return len(text) // 4  # 粗略估算

def _truncate_to_budget(self, items: list[dict], budget: int, key: str) -> list[dict]:
    result, used = [], 0
    for item in items:
        tokens = self._estimate_tokens(str(item.get(key, "")))
        if used + tokens > budget:
            break
        result.append(item)
        used += tokens
    return result
```

总 context budget：约 8000 tokens，分配给各 section。

---

### Phase 6：Skill 系统

**目标**：支持 `/skill-name [args]` 调用可复用的命名工作流，对 Codex 和 Claude Code 都生效。

**影响文件**：
- `backend/app/models/`（新增 `skill.py`）
- `backend/app/api/`（新增 `skills.py`）
- `backend/app/services/conversation_router.py`（识别 `/` 前缀）
- `backend/app/services/run_engine.py`（Codex AGENTS.md 注入）

#### 任务 6.1：数据模型

```python
# backend/app/models/skill.py
class Skill(Base):
    __tablename__ = "skills"

    id = Column(uuid_type(), primary_key=True, default=uuid_default)
    scope = Column(String(20), nullable=False)   # 'global' | 'project'
    project_id = Column(uuid_type(), ForeignKey("projects.id"), nullable=True)
    name = Column(String(100), nullable=False)    # 不含 /，如 'review-pr'
    description = Column(Text, nullable=True)
    prompt_template = Column(Text, nullable=False)
    agent = Column(String(50), nullable=True)     # 偏好的 agent，可为空
    parameters = Column(JSON, default=list)       # [{name, description, required}]
    source = Column(String(50), default="user")  # 'user' | 'claude-skills-dir' | 'agents-md'
    created_at = Column(DateTime, default=datetime.utcnow)
```

#### 任务 6.2：Router 识别 `/skill` 前缀

```python
def _try_expand_skill(self, user_message: str, project_id: str | None) -> dict | None:
    if not user_message.startswith("/"):
        return None

    parts = user_message[1:].split(" ", 1)
    name = parts[0].strip()
    args = parts[1].strip() if len(parts) > 1 else ""

    # 查询：先查项目级，再查全局
    skill = self._find_skill(name, project_id)
    if not skill:
        return None

    expanded = skill.prompt_template.replace("{args}", args)
    return {
        "skill": skill,
        "expanded_prompt": expanded,
        "agent": skill.agent,
    }
```

#### 任务 6.3：Claude Code skill 目录自动发现

当 Project 有 `repo_path` 时，扫描 `.claude/skills/*.md` 并注册为项目级 skill（`source="claude-skills-dir"`）：

```python
def _sync_project_skills(self, project_id: str, repo_path: str):
    skills_dir = Path(repo_path) / ".claude" / "skills"
    if not skills_dir.exists():
        return
    for md_file in skills_dir.glob("*.md"):
        name = md_file.stem
        content = md_file.read_text(encoding="utf-8")
        self._upsert_skill(project_id, name, content, source="claude-skills-dir")
```

#### 任务 6.4：Codex AGENTS.md 注入

在 RunEngine 的 Codex 执行分支，执行前写入临时 AGENTS.md：

```python
def _prepare_codex_context(self, execution_cwd: Path, skill_instructions: str | None):
    # 读项目原始 AGENTS.md（如果有）
    project_agents = (execution_cwd / "AGENTS.md").read_text() \
                     if (execution_cwd / "AGENTS.md").exists() else ""

    # skill 内容追加到 AGENTS.md
    if skill_instructions:
        combined = f"{project_agents}\n\n## Invoked Skill\n{skill_instructions}"
        (execution_cwd / "AGENTS.md").write_text(combined)
```

---

### Phase 7：前端 P0 清理与组件拆分

**目标**：解决"看起来很乱"的问题，把 33K token 的 WorkspaceView 拆分成可维护的组件。

**参考文档**：[`../design/v2_ui_improvement_guide.md`](../design/v2_ui_improvement_guide.md)（详细的 P0/P1/P2 清单）

#### 任务 7.1：P0 删除操作（先删后加）

以下元素全部从 `WorkspaceView.tsx` 移除，不需要替代品：

- 全局导航竖栏中的 COMMAND、PROJECTS、THREADS、RUNS 导航项和圆点
- LOOK 按钮
- 左侧栏的两个输入框（新项目标题、新线程标题）和说明段落
- 顶部"KAM 对话区"标题和所有副标题
- 四个零值统计标签（0 Runs / 0 Compare Sessions 等）
- "发送时自动创建 Run"勾选框
- "带去对比"按钮
- 底部 Status 栏（空状态时）
- 所有技术术语说明段落

完成后：空状态只有图标 + "你在做什么？" + 输入框。

#### 任务 7.2：组件拆分目标结构

```
src/
  features/
    projects/
      ProjectList.tsx
      ProjectCreateModal.tsx
    threads/
      ThreadView.tsx        ← 对话流主视图
      ThreadList.tsx
      MessageBubble.tsx
      MessageInput.tsx      ← 合并为单一卡片（文本区 + 底部工具栏）
    runs/
      RunCard.tsx           ← 四种状态：pending/running/passed/failed
      RunDetailDrawer.tsx   ← 展开的日志/diff/检查结果
      RunCompare.tsx        ← 并排对比视图
    memory/
      MemoryView.tsx        ← 独立视图（偏好/决策/learnings）
    context/
      ContextPanel.tsx      ← 默认隐藏，右侧滑入
  layout/
    AppShell.tsx
    Sidebar.tsx             ← 纯列表：项目 + 线程 + 底部两个入口
```

#### 任务 7.3：P1 新增

- 顶部面包屑（项目名 / 线程名）
- Run 卡片 Passed 状态展示文件列表和测试结果
- Context Panel 单页纵向布局
- Agent 标签改为输入框底部小标签（不是独立下拉区域）

---

### Phase 8：上下文质量提升（长期）

**目标**：保证长对话后 context 质量不退化，Agent 执行时能真正"记得"历史。

#### 任务 8.1：Thread 对话压缩

超过 20 条消息的 thread，对早期消息做摘要压缩：

```python
def _compress_thread_history(self, messages: list, target_count: int = 20) -> str:
    if len(messages) <= target_count:
        return self._summarize_thread_raw(messages)

    # 早期消息 → LLM 摘要为 1 段
    # 保留最近 10 条原文
    early = messages[:-10]
    recent = messages[-10:]

    early_summary = self._call_llm_summarize(early)
    return f"[历史摘要] {early_summary}\n\n[最近对话]\n{self._format_messages(recent)}"
```

#### 任务 8.2：Run Prompt 质量提升

`_build_run_prompt` 改为 AI 生成（而非模板拼接）。在 Phase 1 的 `create_run` tool 里，`task_description` 字段已由对话 AI 生成，这里直接使用，不再需要 `_build_run_prompt` 方法。

#### 任务 8.3：Thread 标题 AI 生成

创建 Thread 时，异步触发一次轻量 LLM 调用生成标题（不阻塞主流程）：

```python
# 第一条消息发送后，异步更新 thread title
async def _generate_thread_title(self, thread_id: str, first_message: str):
    title = await llm.generate(f"用不超过 10 个字概括这个工作：{first_message[:200]}")
    thread_service.update_thread(thread_id, {"title": title})
```

---

## 四、实现顺序与依赖关系

```
Phase 1（对话 AI）
    ↓ 必须先完成
Phase 2（Run digest）← 依赖 Phase 1 的 Anthropic SDK
    ↓
Phase 3（采纳变更）← 独立，可与 Phase 2 并行
Phase 4（SSE 事件 bus）← 独立，可与 Phase 2 并行
Phase 5（Adapter 修复）← 独立，最快完成

Phase 6（Skill 系统）← 依赖 Phase 1（Router 已改造）
Phase 7（前端重构）← 可与 Phase 1-5 并行推进

Phase 8（上下文质量）← 最后，依赖 Phase 1-4 稳定运行
```

**关键路径**：Phase 1 → Phase 2 → Phase 3。这三个 Phase 完成后，产品从"能跑但体验假"变成"真正有用"。

---

## 五、验收标准

### MVP 验收（Phase 1-3 完成后）

- [ ] 用户发消息，AI 以流式文字回复，内容涉及项目历史和记忆（不是模板文字）
- [ ] 用户说"继续昨天的工作"，AI 能说出上次做到哪里
- [ ] Run 执行完成后，thread 里自动出现 AI 生成的结果摘要
- [ ] 点"采纳变更"，代码真正合入项目仓库
- [ ] Run 失败后，AI 解释失败原因并建议下一步

### 完整验收（Phase 1-7 完成后）

- [ ] 给一个从没见过 KAM 的用户看界面截图，他说"打字告诉它我要做什么"
- [ ] `/review-pr`、`/commit` 等 skill 可以被 Codex 和 Claude Code 正确执行
- [ ] 切换到 3 天前的 thread，AI 给出准确的状态恢复摘要
- [ ] Run 执行中能实时看到 stdout 输出（不是等完成后才刷新）
- [ ] 连续使用 1 周后，AI 能在回复中自然引用积累的偏好和决策

---

## 六、不在本路线图范围内

以下功能暂不实现（原因：依赖外部集成或需要独立规划）：

- GitHub / GitLab API 集成（PR review、issue 访问）
- Jira / Linear 集成
- MCP Server（KAM 作为 MCP server 给 Claude Code 提供工具）
- 主动知识提炼（从行为模式中自动归纳偏好）
- 多用户 / 团队协作

---

*文档生成于 2026-03-26，基于当前代码库分析和产品愿景。*
