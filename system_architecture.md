# KAM v2 系统架构

## 1. 架构目标

KAM v2 是一个以对话为中心的个人 AI 指挥台，围绕以下对象工作：

- `Project`：持续性的工作主题
- `Thread`：项目内的一次连贯对话 / 工作流
- `Run`：AI 的一次具体执行
- `Memory`：偏好、决策、项目 learnings 的长期积累

设计原则：

- 对话驱动，而不是表单驱动
- 上下文自动流转，而不是手动快照
- AI 持续工作是默认模式
- 结果可监督，但不要求用户盯着全过程
- 历史偏好、决策与 learnings 可回流到后续执行

## 2. 系统分层

```text
Frontend KAM Workspace
  -> FastAPI API
    -> Conversation Router
    -> Project / Thread / Run / Memory Services
    -> Run Engine
      -> Codex / Claude Code / custom command
        -> SQLite / PostgreSQL / Git worktree / Local storage
```

## 3. 前端结构

- `App.tsx`
  - 默认直接进入 v2 工作台
- `MainLayout`
  - 提供统一壳层与主题能力
- `Sidebar`
  - 展示 KAM 品牌与主导航心智
- `WorkspaceView`
  - 当前主工作区实现
  - 左侧：Projects / Threads
  - 中间：对话流与 Run 卡片
  - 右侧：Project / Memory / Detail / Compare 面板
- `lib/api-v2.ts`
  - 统一 v2 API 客户端
- `types/v2.ts`
  - Project / Thread / Run / Memory / Compare 类型定义

## 4. 后端结构

### 4.1 API

- `backend/app/api/projects.py`
- `backend/app/api/threads.py`
- `backend/app/api/runs.py`
- `backend/app/api/memory.py`

### 4.2 服务

- `project_service.py`
  - 项目 CRUD、资源管理、归档
- `thread_service.py`
  - 线程 CRUD、消息落库
- `conversation_router.py`
  - 用户消息意图判断
  - 调用 LLM 路由或规则路由
  - 自动创建单 Run 或多 Run compare
- `context_assembler.py`
  - 聚合最近对话、资源、决策、偏好、learnings、最近 runs
- `run_service.py`
  - 创建 / 启动 / 重试 / 取消 / 采纳
  - compare 任务编排
- `run_engine.py`
  - 真正执行 agent / custom command
  - 采集 stdout / stderr / summary / changes / patch / check_result / feedback
  - 执行项目级 checks 与自动重试
- `memory_service.py`
  - 读写 preferences / decisions / learnings
  - 关键词搜索

## 5. 数据模型

### 5.1 项目域

- `projects`
- `project_resources`

### 5.2 对话域

- `threads`
- `messages`
- `runs`
- `thread_run_artifacts`

### 5.3 记忆域

- `user_preferences`
- `decision_log`
- `project_learnings`

## 6. 关键行为

### 6.1 Message -> Router -> Run

- 用户向 Thread 发送消息
- Router 判断是纯回复、执行、还是 compare
- Context Assembler 自动拼装上下文
- RunService 创建 Run
- RunEngine 执行并采集产物
- 前端轮询展示最新状态

### 6.2 Run Check Loop

- Run 完成后自动执行项目级 `checkCommands`
- 如果检查失败，生成 `feedback` 注入下一轮 prompt
- 直到通过、取消或达到 `maxRounds`

### 6.3 Memory Feedback Loop

- 对话中的明确偏好可自动提取
- 手工记录决策与项目 learnings
- 后续执行自动注入相关偏好、决策与 learnings

### 6.4 Compare

- 同一个 Thread 下可并发创建多个 Run
- 每个 Run 带 `compareGroupId` / `compareLabel`
- 前端按 compare group 聚合展示状态与摘要

## 7. 运维约束

- SQLite 用于本地开发
- PostgreSQL 适合长期运行环境
- 前端静态产物由 FastAPI 直接托管
- 旧 Lite 路由暂时保留在仓库中，但不再是默认交互路径
