# KAM Lite 系统架构

## 1. 架构目标

KAM Lite 是一个单体式任务工作台，围绕以下对象工作：

- `TaskCard`
- `TaskRef`
- `ContextSnapshot`
- `AgentRun`
- `RunArtifact`

设计原则：

- 单库优先
- 外部 Agent 复用优先
- 平台只做调度、记录、收口
- 不承担额外独立工作台职责

## 2. 系统分层

```text
Frontend Task Workspace
  -> FastAPI Lite Core API
    -> Workspace Service
    -> Run Executor
      -> Codex / Claude Code / custom command
        -> Local storage / Git worktree / PostgreSQL
```

## 3. 前端结构

- `App.tsx` 直接加载唯一任务工作台
- `MainLayout` 提供 Lite 壳层
- `Sidebar` 只展示产品定位与外观设置
- `TasksView` 承担任务、引用、run、review、artifacts 全部交互
- `lib/api.ts` 只保留 Lite Core API 客户端

## 4. 后端结构

### 4.1 API

- `backend/app/api/tasks.py`

### 4.2 服务

- `workspace_service.py`
  - 任务 CRUD
  - 引用管理
  - Context Snapshot 生成
  - review / compare 聚合
- `run_executor.py`
  - 外部 Agent 启动
  - 运行目录与 worktree 管理
  - stdout/stderr/summary/changes/patch 采集

### 4.3 数据模型

#### `task_cards`

- 任务标题、描述、状态、优先级、标签、metadata

#### `task_refs`

- 任务引用
- 支持 URL、repo-path、file、work-item、doc、pr 等自由类型

#### `context_snapshots`

- 仅保存 `{ task, refs, recentRuns }`

#### `agent_runs`

- Agent 名称、类型、状态、工作目录、prompt、command、metadata

#### `run_artifacts`

- `prompt`
- `context`
- `plan`
- `stdout`
- `stderr`
- `summary`
- `changes`
- `patch`

## 5. 关键行为

### 5.1 Context Resolve

输入：

- 当前任务
- 任务 refs
- 最近 runs

输出：

- 快照摘要
- 快照 JSON 数据

### 5.2 Run Execution

- 创建 run 时自动生成 prompt、context、plan artifacts
- 执行器按 Agent 类型拉起 CLI
- 若检测到 Git 仓库，自动采集 changes 与 patch
- 平台只展示 patch，不负责直接应用

### 5.3 Review / Compare

- Review 汇总任务下所有 runs 与 artifacts
- Compare 返回每个 run 的状态、artifact 数、变更文件数、untracked 数、patch 存在性

## 6. 运维约束

- SQLite 可用于本地开发
- PostgreSQL 用于长期运行环境
- 使用 `backend/scripts/reset_lite_core_schema.py` 做破坏式 schema reset
- 历史模块表不再保留
