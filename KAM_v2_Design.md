# KAM v2 — 个人 AI 指挥台 产品与架构设计方案

> 版本：v2.0-draft  
> 日期：2026-03-25  
> 作者：KAM Team

---

## 一、产品重新定义

### 1.1 一句话定位

KAM 是一个**可以长时间指挥 AI 工作的个人控制台**——你的外置大脑和 AI 参谋长。

### 1.2 它是什么 / 不是什么

| KAM 是 | KAM 不是 |
|--------|----------|
| 你和 AI 之间的持久工作界面 | 又一个聊天窗口 |
| 能记住你所有项目上下文的外置大脑 | 知识管理平台 / Notion 替代品 |
| 能并发调度多个 Agent 的指挥台 | CI/CD 系统 |
| 一个人的作战室 | 团队协作工具 |

### 1.3 核心场景

**场景 A — 持续开发指挥**

你打开 KAM，看到你的项目"重构认证模块"还开着。你说"继续昨天的工作，先把 OAuth 的 token 刷新逻辑写完"。KAM 自动把昨天的进度、相关文件、你之前的决策记录拼成上下文，调起 Claude Code 开始工作。你去喝咖啡，回来看到 AI 已经完成了三轮迭代，测试全部通过。你扫一眼变更，点一下采纳。

**场景 B — 研究与决策**

你在评估要不要引入某个新框架。你开一个项目"技术选型：状态管理"，让 AI 分别研究 Zustand、Jotai、Valtio，各出一份分析报告。三个 Agent 并发执行，结果放在一起对比。你标注自己的倾向，AI 帮你写出最终决策文档。下次有人问"为什么选 Zustand"，KAM 记得整个决策过程。

**场景 C — 日常助理**

你说"帮我整理一下这周的 PR review 意见，汇总成周报"。KAM 知道你的 GitHub 仓库在哪、你的周报格式是什么样的，直接生成。

### 1.4 设计原则

1. **对话驱动，而非表单驱动** — 用户用自然语言指挥，系统自动编排执行
2. **上下文自动流转** — 用户不需要手动"创建快照"或"添加引用"，系统自己追踪
3. **AI 持续工作是默认模式** — 不需要专门启动"自治会话"，AI 默认迭代到完成
4. **可监督但不需要盯着** — 用户可以离开，回来检查结果即可
5. **积累记忆** — 每次交互都让 KAM 更了解你

---

## 二、概念模型重构

### 2.1 v1 vs v2 概念对比

v1 有 7 个暴露给用户的核心概念：TaskCard、TaskRef、ContextSnapshot、AgentRun、RunArtifact、AutonomySession、AutonomyCycle。用户在操作前必须理解所有这些概念以及它们之间的关系。

v2 将概念大幅简化。暴露给用户的只有 3 个：

```
用户可见概念（3 个）：
  Project  — 一个持续性的工作主题
  Thread   — 项目内一次连贯的对话/工作流
  Run      — AI 的一次执行（通常自动触发，用户只看结果）

系统内部概念（用户无需了解）：
  Context  — 系统自动从 Project 历史中组装
  Memory   — 跨项目的用户偏好与知识积累
  Check    — 自动验收机制（内置于 Run 生命周期）
```

### 2.2 概念关系

```
Memory（全局）
  │
  ├─ Project A
  │    ├─ Thread 1 （"把登录页重写成 React"）
  │    │    ├─ 用户消息 + AI 回复
  │    │    ├─ Run（Claude Code 执行）
  │    │    ├─ Run（测试验证）
  │    │    └─ Run（修复 lint 错误）
  │    ├─ Thread 2 （"加上 Google SSO"）
  │    │    └─ ...
  │    └─ 项目元数据（仓库路径、相关文档、决策记录）
  │
  ├─ Project B
  │    └─ ...
  │
  └─ 全局偏好（代码风格、常用技术栈、工作习惯）
```

### 2.3 核心概念详解

#### Project（项目）

项目是 KAM 的顶层组织单位。它不是"任务"——任务意味着完成就结束了；项目是持续存在的工作上下文。

```
Project:
  id: string
  title: string                    # "重构认证模块"
  status: active | paused | done
  repo_path?: string               # 关联的代码仓库
  description?: string             # 项目目标和约束
  pinned_resources: Resource[]     # 钉住的重要文档/链接/文件
  created_at: datetime
  updated_at: datetime
```

**关键区别**：v1 的"引用（TaskRef）"现在变成了项目的 `pinned_resources`，不再是独立实体。用户在对话中提到的链接、文件自动被项目记住，重要的可以手动钉住。

#### Thread（对话线程）

Thread 是项目内的一次连贯工作流。它取代了 v1 中 AutonomySession 的角色，但更自然——它就是一段对话，只是这段对话中 AI 可以自动执行、验证、迭代。

```
Thread:
  id: string
  project_id: string
  title: string                    # 自动生成或用户命名
  status: active | completed | failed | paused
  messages: Message[]              # 用户消息 + AI 回复 + 系统事件
  created_at: datetime
```

```
Message:
  id: string
  role: user | assistant | system
  content: string
  runs: Run[]                      # 该消息触发的执行
  timestamp: datetime
```

#### Run（执行）

Run 是 AI 的一次具体执行，对应实际调用 Agent（Claude Code / Codex / 自定义命令）。Run 通常由 Thread 中的对话自动触发，用户不需要手动"创建 Run"。

```
Run:
  id: string
  thread_id: string
  agent: "claude-code" | "codex" | "custom"
  command?: string                 # custom 时的命令
  status: pending | running | checking | passed | failed | cancelled
  work_dir: string                 # 工作目录
  artifacts:                       # 结构化产出
    prompt: string
    stdout: string
    stderr: string
    summary?: string
    changes?: FileDiff[]
    patch?: string
  check_results?: CheckResult[]    # 自动验收结果
  duration_ms: number
  created_at: datetime
```

**关键设计**：Run 内置了检查（check）环节。不再需要独立的 AutonomyCycle。执行完成后自动运行检查，失败则自动生成反馈并开始下一轮 Run，直到通过或达到上限。这个循环对用户来说就是"AI 在工作中"。

#### Memory（记忆）

这是 v1 完全缺失、但对"外置大脑"定位至关重要的概念。

```
Memory:
  user_preferences:                # 用户偏好
    code_style: string             # "prefer functional, avoid classes"
    tech_stack: string[]           # ["React", "FastAPI", "PostgreSQL"]
    conventions: string[]          # ["use pnpm not npm", "tests in __tests__/"]
  
  project_learnings: Learning[]    # 项目中积累的知识
    project_id: string
    content: string                # "OAuth token 刷新需要处理 race condition"
    source_thread_id: string
    
  decision_log: Decision[]         # 决策记录
    project_id?: string
    question: string               # "状态管理方案选哪个？"
    decision: string               # "选 Zustand"
    reasoning: string              # "轻量、API 简单、生态够用"
    date: datetime
```

---

## 三、交互设计

### 3.1 整体布局

```
┌──────────────────────────────────────────────────────────┐
│  KAM                          [⚙ Settings] [👤 Profile] │
├────────────┬─────────────────────────────────────────────┤
│            │                                             │
│  PROJECTS  │              MAIN AREA                      │
│            │                                             │
│  ┌──────┐  │  ┌─────────────────────────────────────┐   │
│  │ 🟢 P1│  │  │                                     │   │
│  │   P2 │  │  │         Thread 对话区                │   │
│  │   P3 │  │  │                                     │   │
│  │   P4 │  │  │    用户消息、AI 回复、                │   │
│  │      │  │  │    Run 状态卡片、结果预览             │   │
│  └──────┘  │  │                                     │   │
│            │  │                                     │   │
│  THREADS   │  │                                     │   │
│  ┌──────┐  │  │                                     │   │
│  │  T1  │  │  ├─────────────────────────────────────┤   │
│  │  T2  │  │  │  💬 输入区                           │   │
│  │  T3  │  │  │  [附件] [Agent 选择] [发送]          │   │
│  └──────┘  │  └─────────────────────────────────────┘   │
│            │                                             │
│  [+ New]   │  CONTEXT PANEL (可收起)  ──────────────────│
│            │  📁 文件树 | 📊 Run 状态 | 📝 变更预览     │
├────────────┴─────────────────────────────────────────────┤
│  Status: Claude Code running on P1 · 2 runs active      │
└──────────────────────────────────────────────────────────┘
```

### 3.2 布局区域说明

**左侧栏 — 导航**

只有两级：项目列表 → 线程列表。当前活跃的项目有绿点标识。点击项目展开其下的线程。底部有"新建项目"按钮。这里不放任何设置、统计或管理功能。

**主区域 — 对话流**

这是用户 90% 时间注视的区域。它是一个增强版的对话界面，但消息流中可以内嵌：

- **Run 状态卡片**：显示 Agent 正在执行的任务、当前状态、已用时间。点击展开可看到实时日志。
- **结果预览卡片**：Run 完成后内联显示 summary、变更文件列表、测试通过状态。点击可展开完整 diff。
- **决策节点**：当 AI 需要用户确认时（比如"两个方案你选哪个"），以交互式卡片呈现。
- **系统事件**：轻量地穿插在对话中（"第 2 轮验证通过，所有测试绿了"）。

**底部输入区**

默认就是文本输入框。可以附加文件、选择 Agent（默认自动选择）。快捷键 `Cmd+Enter` 发送。

**右侧/底部 — 上下文面板（可收起）**

这是"外置大脑"的物理体现。平时可以收起来不占空间，需要时拉出来查看：

- **文件树**：当前项目关联的代码仓库文件结构
- **Run 仪表盘**：所有活跃和最近的 Run 状态
- **变更预览**：正在进行或已完成的代码变更 diff 视图
- **钉住的资源**：项目的关键文档、链接

### 3.3 核心交互流程

#### 流程 A：开始新工作

```
用户 → 点击 "+ New Project" 或直接在首页说话
用户 → "我要重构用户认证模块，用 OAuth2 + JWT"
系统 → 自动创建 Project，提取关键信息
  AI → "好的，我创建了项目'重构用户认证'。
         我看到你的仓库里有 auth/ 目录，
         要从这里开始吗？先帮你分析现有代码？"
用户 → "好，先分析，然后给我一个重构方案"
系统 → 触发 Run（分析代码） → 完成后 AI 呈现方案
用户 → "方案 B 好，开始做吧"
系统 → 记录决策 → 触发 Run（开始编码） → AI 自动迭代
```

**关键区别**：用户全程在对话，不需要去"创建任务卡"、"添加引用"、"生成快照"。这些事系统在后台自动完成了。

#### 流程 B：回到进行中的工作

```
用户 → 打开 KAM，看到 Project 列表
     → 点击"重构用户认证"
     → 看到上次的 Thread 和最新状态
  AI → "上次我们完成了 OAuth token 签发，
         测试全过了。还剩 token 刷新和吊销两块。
         要继续吗？"
用户 → "继续，先做刷新"
系统 → 自动携带之前的上下文 → 触发 Run
```

#### 流程 C：并发执行 + 对比

```
用户 → "用 Codex 和 Claude Code 分别实现这个功能，我要对比"
系统 → 同时触发两个 Run
     → 对话流中出现两个并排的 Run 状态卡片
     → 完成后出现对比视图（diff、测试结果、代码风格对比）
用户 → 点选采纳其中一个
系统 → 记录决策
```

### 3.4 对话中的 Run 展示

Run 在对话流中以卡片形式内联展示，不是跳转到另一个页面：

```
┌─ Run #3 ─────────────────────────────────── claude-code ─┐
│  🟢 Passed · 3 rounds · 47s                              │
│                                                           │
│  Summary: 实现了 token 刷新接口，添加了 race condition    │
│           保护。修改了 3 个文件，新增 2 个测试。          │
│                                                           │
│  Changes: auth/refresh.py (+45 -12)                       │
│           auth/middleware.py (+8 -3)                       │
│           tests/test_refresh.py (+67 new)                 │
│                                                           │
│  Tests: ✅ 14/14 passed                                   │
│                                                           │
│  [查看完整 Diff]  [查看日志]  [采纳变更]  [重试]          │
└───────────────────────────────────────────────────────────┘
```

---

## 四、系统架构

### 4.1 总体分层

```
┌─────────────────────────────────────────────────┐
│                   Frontend                       │
│              React + TypeScript                  │
│   ┌──────────┬──────────┬───────────────────┐   │
│   │ Project  │ Thread   │ Context           │   │
│   │ Nav      │ Chat     │ Panel             │   │
│   └──────────┴──────────┴───────────────────┘   │
│              │ SSE / REST                        │
├──────────────┼──────────────────────────────────┤
│              │       Backend (FastAPI)            │
│   ┌──────────┴──────────────────────────────┐   │
│   │           Conversation Router            │   │
│   │   (解析意图 → 决定是否触发 Run)          │   │
│   ├─────────────────────────────────────────┤   │
│   │              Core Services               │   │
│   │  ┌─────────┬──────────┬──────────────┐  │   │
│   │  │ Project │ Thread   │ Memory       │  │   │
│   │  │ Service │ Service  │ Service      │  │   │
│   │  └─────────┴──────────┴──────────────┘  │   │
│   │  ┌─────────┬──────────────────────────┐ │   │
│   │  │ Run     │ Context                  │ │   │
│   │  │ Engine  │ Assembler                │ │   │
│   │  └─────────┴──────────────────────────┘ │   │
│   ├─────────────────────────────────────────┤   │
│   │          Agent Adapters                  │   │
│   │  ┌───────────┬───────────┬───────────┐  │   │
│   │  │ Claude    │ Codex     │ Custom    │  │   │
│   │  │ Code      │ Adapter   │ Command   │  │   │
│   │  └───────────┴───────────┴───────────┘  │   │
│   ├─────────────────────────────────────────┤   │
│   │          Storage Layer                   │   │
│   │  ┌──────────┬───────────┬────────────┐  │   │
│   │  │ SQLite / │ File      │ Git        │  │   │
│   │  │ Postgres │ Storage   │ Integration│  │   │
│   │  └──────────┴───────────┴────────────┘  │   │
│   └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

### 4.2 核心模块职责

#### Conversation Router（对话路由器）

这是 v2 最重要的新增模块。它负责理解用户意图并决定下一步行动。

```
输入：用户消息 + 当前 Thread 上下文
输出：以下之一或组合：
  - 纯文本回复（闲聊、解释、讨论）
  - 触发 Run（需要 Agent 执行的操作）
  - 项目操作（创建/切换项目、钉住资源）
  - 记忆操作（记录偏好、决策）
  - 并发 Run（用户要求对比多个 Agent）
```

实现方式：用 LLM 做意图识别 + function calling。系统提示中包含当前项目上下文和可用操作列表。

#### Context Assembler（上下文组装器）

取代 v1 的手动 Context Snapshot。每次需要调用 Agent 时，自动组装上下文：

```python
def assemble_context(thread_id: str) -> Context:
    thread = get_thread(thread_id)
    project = get_project(thread.project_id)
    
    context = Context()
    
    # 1. 项目级上下文
    context.add(project.description)
    context.add(project.pinned_resources)
    
    # 2. 当前 Thread 对话摘要（最近 N 条 + 关键决策）
    context.add(summarize_thread(thread))
    
    # 3. 最近 Run 的结果摘要（不是全部日志，只是 summary）
    recent_runs = get_recent_runs(thread_id, limit=3)
    context.add([r.artifacts.summary for r in recent_runs])
    
    # 4. 全局记忆中的相关偏好
    context.add(get_relevant_preferences(project))
    
    # 5. 相关的历史决策
    context.add(get_relevant_decisions(project))
    
    return context
```

#### Run Engine（执行引擎）

统一管理 Run 的生命周期，包括内置的自动验收循环：

```
                  ┌──────────┐
                  │  Pending  │
                  └─────┬────┘
                        │ start
                  ┌─────▼────┐
              ┌───│ Running  │
              │   └─────┬────┘
              │         │ complete
              │   ┌─────▼────┐
              │   │ Checking │──── 检查命令配置在 Project 上
              │   └─────┬────┘
              │    pass/ │ \fail
              │   ┌─────▼┐ ┌▼─────────┐
              │   │Passed│ │ 自动重试   │─── 把失败反馈注入下一轮
              │   └──────┘ │（max N轮）│    prompt，重新 Running
              │            └───────────┘
              │ error/timeout
              ┌─────▼────┐
              │  Failed   │
              └──────────┘
```

**关键设计**：检查命令（lint、test、type-check 等）配置在 Project 级别，不需要每次手动设定。Run Engine 自动执行检查循环，对用户来说就是"Run 在跑"，跑完要么绿了，要么告诉你哪里不行。

#### Memory Service（记忆服务）

负责持久化和检索用户的知识积累：

```
Memory Service 职责：
  1. 偏好提取：从对话中识别并记录用户偏好
     - "我不喜欢 class 组件" → 记录代码偏好
     - "用 pnpm" → 记录工具偏好
  
  2. 决策记录：当用户在多个方案间做出选择时，记录决策和理由
  
  3. 知识索引：对每个 Thread 的关键结论建立索引
     - 基于 embedding 的相似度检索
     - 新 Thread 开始时自动检索相关历史知识
  
  4. 上下文注入：在组装 Context 时提供相关记忆
```

### 4.3 数据模型（完整版）

```sql
-- 项目
CREATE TABLE projects (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    status      TEXT DEFAULT 'active',  -- active / paused / done
    repo_path   TEXT,                   -- 关联仓库路径
    description TEXT,
    check_commands TEXT,                -- JSON: ["npm test", "npm run lint"]
    settings    TEXT,                   -- JSON: 项目级配置
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 项目钉住的资源
CREATE TABLE project_resources (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id),
    type        TEXT NOT NULL,          -- url / file / repo-path / doc / note
    title       TEXT,
    uri         TEXT NOT NULL,          -- 实际地址或内容
    pinned      BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 对话线程
CREATE TABLE threads (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id),
    title       TEXT,
    status      TEXT DEFAULT 'active',  -- active / completed / failed / paused
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 消息
CREATE TABLE messages (
    id          TEXT PRIMARY KEY,
    thread_id   TEXT REFERENCES threads(id),
    role        TEXT NOT NULL,          -- user / assistant / system
    content     TEXT NOT NULL,
    metadata    TEXT,                   -- JSON: 附加信息
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 执行
CREATE TABLE runs (
    id              TEXT PRIMARY KEY,
    thread_id       TEXT REFERENCES threads(id),
    message_id      TEXT REFERENCES messages(id),  -- 触发这个 Run 的消息
    agent           TEXT NOT NULL,      -- claude-code / codex / custom
    command         TEXT,               -- custom 命令
    status          TEXT DEFAULT 'pending',
    work_dir        TEXT,
    round           INTEGER DEFAULT 1, -- 当前是第几轮（自动重试计数）
    max_rounds      INTEGER DEFAULT 5,
    duration_ms     INTEGER,
    error           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP
);

-- 执行产出
CREATE TABLE run_artifacts (
    id          TEXT PRIMARY KEY,
    run_id      TEXT REFERENCES runs(id),
    type        TEXT NOT NULL,          -- prompt / stdout / stderr / summary / changes / patch / check_result
    content     TEXT NOT NULL,
    round       INTEGER DEFAULT 1,     -- 属于哪一轮
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 记忆 — 用户偏好
CREATE TABLE user_preferences (
    id          TEXT PRIMARY KEY,
    category    TEXT NOT NULL,          -- code_style / tool / convention / general
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    source_thread_id TEXT,             -- 从哪个对话中提取的
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

-- 记忆 — 决策日志
CREATE TABLE decision_log (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id),
    question        TEXT NOT NULL,
    decision        TEXT NOT NULL,
    reasoning       TEXT,
    source_thread_id TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 记忆 — 项目知识
CREATE TABLE project_learnings (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id),
    content         TEXT NOT NULL,
    embedding       BLOB,              -- 向量，用于相似度检索
    source_thread_id TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.4 API 设计

```
# 项目
GET    /api/projects                    # 项目列表
POST   /api/projects                    # 创建项目
GET    /api/projects/:id                # 项目详情
PUT    /api/projects/:id                # 更新项目
POST   /api/projects/:id/archive        # 归档项目

# 项目资源
GET    /api/projects/:id/resources      # 资源列表
POST   /api/projects/:id/resources      # 添加资源
DELETE /api/projects/:id/resources/:rid  # 删除资源

# 线程
GET    /api/projects/:id/threads        # 线程列表
POST   /api/projects/:id/threads        # 新建线程（也可通过对话自动创建）
GET    /api/threads/:id                 # 线程详情（含消息历史）

# 对话（核心入口）
POST   /api/threads/:id/messages        # 发送消息
  → 返回 AI 回复 + 可能触发的 Run
  → SSE 流式返回

# Run
GET    /api/threads/:id/runs            # 线程内所有 Run
GET    /api/runs/:id                    # Run 详情
GET    /api/runs/:id/artifacts          # Run 产出
GET    /api/runs/:id/events             # Run 事件流（SSE）
POST   /api/runs/:id/cancel             # 取消 Run
POST   /api/runs/:id/retry              # 手动重试
POST   /api/runs/:id/adopt              # 采纳变更

# 对比
POST   /api/threads/:id/compare         # 对比线程内多个 Run

# 记忆
GET    /api/memory/preferences          # 查看所有偏好
PUT    /api/memory/preferences/:id      # 修改偏好
GET    /api/memory/decisions             # 决策日志
GET    /api/memory/search               # 知识检索（语义搜索）
```

### 4.5 通信机制

```
消息发送流程：

  前端                          后端
   │                             │
   │  POST /threads/:id/messages │
   │  ───────────────────────►   │
   │                             │  1. 保存用户消息
   │                             │  2. Conversation Router 判断意图
   │                             │  3. Context Assembler 组装上下文
   │  SSE: AI 文本回复（流式）    │  4. 调 LLM 生成回复
   │  ◄───────────────────────   │
   │  SSE: run_created           │  5. 如果需要执行，创建 Run
   │  ◄───────────────────────   │
   │  SSE: run_progress          │  6. Run 执行中的进度
   │  ◄───────────────────────   │
   │  SSE: run_check_progress    │  7. 检查进度
   │  ◄───────────────────────   │
   │  SSE: run_completed         │  8. Run 完成
   │  ◄───────────────────────   │
   │  SSE: thread_done           │  9. 本轮对话完成
   │  ◄───────────────────────   │
```

---

## 五、前端架构

### 5.1 技术栈

```
React 18+ (TypeScript)
状态管理：Zustand（轻量、简单）
路由：React Router
样式：Tailwind CSS
实时通信：SSE (EventSource)
Markdown 渲染：react-markdown
代码高亮：Shiki
Diff 展示：react-diff-viewer
```

### 5.2 组件结构

```
src/
  app/
    App.tsx                    # 根组件，路由
    layout/
      AppShell.tsx             # 整体布局框架
      Sidebar.tsx              # 左侧项目/线程导航
      ContextPanel.tsx         # 右侧可收起的上下文面板
      StatusBar.tsx            # 底部状态栏

  features/
    projects/
      ProjectList.tsx          # 项目列表
      ProjectCreate.tsx        # 创建项目（轻量模态框）
      ProjectSettings.tsx      # 项目设置
    
    threads/
      ThreadView.tsx           # 线程主视图（对话流）
      ThreadList.tsx           # 线程列表
      MessageInput.tsx         # 输入区
      MessageBubble.tsx        # 单条消息
    
    runs/
      RunCard.tsx              # 对话中内联的 Run 卡片
      RunDetailDrawer.tsx      # 展开的 Run 详情抽屉
      RunLog.tsx               # 实时日志
      RunDiff.tsx              # 变更 Diff 视图
      RunCompare.tsx           # 多 Run 对比
    
    context/
      FileTree.tsx             # 仓库文件树
      ResourceList.tsx         # 钉住的资源
      RunDashboard.tsx         # Run 状态概览
    
    memory/
      PreferencesView.tsx      # 查看/编辑偏好
      DecisionLog.tsx          # 决策历史

  lib/
    api.ts                     # API 客户端
    sse.ts                     # SSE 连接管理
    store.ts                   # Zustand store
    types.ts                   # TypeScript 类型定义
```

### 5.3 状态管理

```typescript
// store.ts — Zustand store
interface KAMStore {
  // 项目
  projects: Project[]
  activeProjectId: string | null
  
  // 线程
  threads: Thread[]               // 当前项目的线程
  activeThreadId: string | null
  
  // 消息
  messages: Message[]             // 当前线程的消息
  isStreaming: boolean            // AI 正在回复
  
  // Run
  activeRuns: Run[]               // 正在执行的 Run
  
  // 上下文面板
  contextPanelOpen: boolean
  contextPanelTab: 'files' | 'runs' | 'resources'
  
  // Actions
  sendMessage: (content: string, attachments?: File[]) => Promise<void>
  cancelRun: (runId: string) => Promise<void>
  adoptRun: (runId: string) => Promise<void>
  // ...
}
```

---

## 六、后端架构

### 6.1 技术栈

```
Python 3.11+
Web 框架：FastAPI
数据库：SQLite（开发） / PostgreSQL（生产）
ORM：SQLAlchemy 2.0
任务队列：内置 asyncio（单机）/ Redis + Celery（扩展时）
向量存储：sqlite-vss 或 pgvector
LLM 调用：Anthropic SDK / OpenAI SDK
```

### 6.2 目录结构

```
backend/
  app/
    main.py                        # FastAPI 入口
    
    api/
      projects.py                  # 项目 API
      threads.py                   # 线程 + 消息 API
      runs.py                      # Run API
      memory.py                    # 记忆 API
    
    services/
      conversation_router.py       # 对话路由（意图识别 + 编排）
      context_assembler.py         # 上下文自动组装
      run_engine.py                # Run 生命周期管理
      memory_service.py            # 记忆存取 + 偏好提取
      project_service.py           # 项目 CRUD
      thread_service.py            # 线程 CRUD
    
    agents/
      base.py                      # Agent 适配器基类
      claude_code.py               # Claude Code 适配器
      codex.py                     # Codex 适配器
      custom.py                    # 自定义命令适配器
    
    models/
      project.py
      thread.py
      message.py
      run.py
      memory.py
    
    core/
      config.py                    # 配置
      database.py                  # 数据库连接
      events.py                    # SSE 事件管理
      git_utils.py                 # Git 操作工具
```

### 6.3 Conversation Router 详细设计

这是整个系统的"大脑"，决定如何响应每条用户消息：

```python
class ConversationRouter:
    """
    解析用户意图，编排响应和执行。
    """
    
    async def route(self, thread_id: str, user_message: str) -> RouterResult:
        thread = await self.thread_service.get(thread_id)
        project = await self.project_service.get(thread.project_id)
        
        # 1. 组装路由上下文（比完整 Agent 上下文更轻量）
        routing_context = RoutingContext(
            project_summary=project.description,
            recent_messages=thread.messages[-10:],
            active_runs=await self.run_engine.get_active(thread_id),
            available_agents=self.get_available_agents(),
        )
        
        # 2. 调用 LLM 判断意图
        intent = await self.classify_intent(user_message, routing_context)
        
        # 3. 根据意图编排动作
        match intent:
            case Intent.CHAT:
                # 纯对话，直接回复
                return await self.generate_reply(thread, user_message)
            
            case Intent.EXECUTE:
                # 需要 Agent 执行
                context = await self.context_assembler.assemble(thread_id)
                reply = await self.generate_reply(thread, user_message)
                run = await self.run_engine.create_and_start(
                    thread_id=thread_id,
                    agent=intent.agent,
                    prompt=intent.task_description,
                    context=context,
                )
                return RouterResult(reply=reply, runs=[run])
            
            case Intent.COMPARE:
                # 并发执行多个 Agent
                context = await self.context_assembler.assemble(thread_id)
                runs = []
                for agent in intent.agents:
                    run = await self.run_engine.create_and_start(
                        thread_id=thread_id,
                        agent=agent,
                        prompt=intent.task_description,
                        context=context,
                    )
                    runs.append(run)
                reply = await self.generate_reply(thread, user_message)
                return RouterResult(reply=reply, runs=runs)
            
            case Intent.REMEMBER:
                # 记录偏好或决策
                await self.memory_service.record(intent.memory_item)
                return await self.generate_reply(thread, user_message)
            
            case Intent.PROJECT_ACTION:
                # 项目操作（创建、切换、归档等）
                await self.handle_project_action(intent.action)
                return await self.generate_reply(thread, user_message)
```

---

## 七、迁移策略

### 7.1 渐进式迁移，不破坏式重写

从 v1 到 v2 不建议推翻重来，而是分阶段演进：

**Phase 1 — 概念映射与数据迁移（1 周）**

```
v1 TaskCard     →  v2 Project（一对一映射）
v1 TaskRef      →  v2 project_resources
v1 AgentRun     →  v2 Run（保留核心字段）
v1 RunArtifact  →  v2 run_artifacts
v1 AutonomySession → 删除（Run 内置自动迭代）
v1 AutonomyCycle   → 删除（合并到 run_artifacts 的 round 字段）
新增：threads, messages, user_preferences, decision_log, project_learnings
```

写迁移脚本将现有数据映射到新表。

**Phase 2 — 对话层（2 周）**

- 实现 Thread + Message 模型
- 实现 Conversation Router（先用简单规则，后期换 LLM）
- 实现基础的对话 UI
- 把现有的"创建 Run"流程包装成对话触发
- 此阶段结束后：用户可以通过对话创建和管理 Run

**Phase 3 — 上下文自动化（1 周）**

- 实现 Context Assembler
- 删除手动"创建快照"流程
- 删除手动"添加引用"流程（改为自动提取 + 手动钉住）
- 此阶段结束后：用户不再需要手动管理上下文

**Phase 4 — 内置自动迭代（1 周）**

- 把 AutonomySession/Cycle 的逻辑合并到 Run Engine
- Run 完成后自动执行检查、自动重试
- 删除独立的 Autonomy 面板
- 此阶段结束后：AI 默认工作到完成

**Phase 5 — 记忆系统（2 周）**

- 实现 Memory Service
- 偏好自动提取
- 决策记录
- 知识索引（embedding）
- 此阶段结束后：KAM 能记住用户的偏好和历史

**Phase 6 — 打磨体验（持续）**

- UI 细节打磨
- 快捷键
- 离线状态恢复
- 性能优化

### 7.2 每个 Phase 的验收标准

| Phase | 验收标准 |
|-------|---------|
| 1 | 旧数据成功迁移到新表，无数据丢失 |
| 2 | 用户可以通过对话创建项目、发起 Run、查看结果 |
| 3 | 创建 Run 时无需手动操作，上下文自动组装 |
| 4 | Run 失败后自动重试，无需手动启动自治会话 |
| 5 | AI 回复中能引用用户的历史偏好和决策 |
| 6 | 完整流程下来用户体验流畅自然 |

---

## 八、与 v1 的差异总结

| 维度 | v1 (KAM Lite) | v2 (KAM) |
|------|--------------|-----------|
| 交互方式 | 表单驱动（创建 → 填写 → 执行） | 对话驱动（说话 → 系统编排） |
| 核心概念 | 7 个暴露给用户 | 3 个暴露给用户 |
| 上下文管理 | 手动创建快照 | 自动组装 |
| 自治执行 | 独立模式，需手动启动 | 内置行为，默认开启 |
| 记忆能力 | 无 | 偏好、决策、知识积累 |
| 布局 | 大工作台塞所有功能 | 对话为主 + 可收起上下文面板 |
| 用户心智模型 | "操作一个任务管理系统" | "和一个记得一切的 AI 助手对话" |

---

## 九、风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| Conversation Router 的意图识别不准 | 用户说要执行但 AI 只回了文本 | Phase 2 先用规则引擎兜底，逐步加入 LLM；提供手动触发 Run 的快捷入口作为备选 |
| 自动上下文太长，超出 Agent 的 context window | Agent 执行质量下降 | Context Assembler 做摘要压缩；设置 token 预算；优先级排序 |
| 记忆系统提取出错误偏好 | AI 行为不符合预期 | 记忆可见、可编辑；重要偏好需要用户确认 |
| 迁移过程中丢失用户数据 | 用户信任受损 | 迁移前完整备份；迁移脚本有回滚能力 |
| 自动重试循环卡住（一直失败但不停） | 浪费 Agent 调用、用户等待 | 严格的 max_rounds 限制（默认 5）；连续相似错误提前终止；通知用户介入 |

---

*文档结束。此方案作为 KAM v2 的设计蓝图，具体实现细节在各 Phase 的执行过程中进一步细化。*
