# KAM Lite 系统架构

## 1. 架构目标

KAM Lite 是一个单体式任务工作台，围绕以下对象工作：

- `TaskCard`
- `TaskRef`
- `ContextSnapshot`
- `AgentRun`
- `RunArtifact`
- `AutonomySession`
- `AutonomyCycle`

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
    -> Autonomy Service / Manager
      -> Codex / Claude Code / custom command
        -> Local storage / Git worktree / PostgreSQL
```

## 3. 前端结构

- `App.tsx` 直接加载唯一任务工作台
- `MainLayout` 提供 Lite 壳层
- `Sidebar` 只展示产品定位与外观设置
- `TasksView` 承担任务、引用、run、review、artifacts 全部交互
- `AutonomyPanel` 承担自治会话、检查结果、指标展示与 dogfooding 入口
- `lib/api.ts` 只保留 Lite Core API 客户端

## 4. 后端结构

### 4.1 API

- `backend/app/api/tasks.py`
- `backend/app/api/autonomy.py`

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
- `autonomy_service.py`
  - 自治会话 CRUD
  - dogfooding 模板
  - 指标聚合
- `autonomy_manager.py`
  - 自动迭代 worker run
  - 执行检查命令
  - 记录 cycle 结果与反馈

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

#### `autonomy_sessions`

- 自治会话配置
- 主 Agent / 最大轮次 / 成功标准 / 检查命令
- 打断次数与最终状态

#### `autonomy_cycles`

- 每一轮自治迭代记录
- 关联 worker run
- 检查结果与失败反馈

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

### 5.4 Autonomy Loop

- 会话启动后自动创建 worker run
- worker run 结束后自动执行检查命令
- 如果检查失败，系统把反馈拼进下一轮 prompt appendix
- 直到：
  - 所有检查通过
  - 用户打断
  - 达到最大轮次

### 5.5 Autonomy Metrics

- `autonomyCompletionRate`
  - 终态会话中，未被打断且最终完成的占比
- `interruptionRate`
  - 终态会话中，被用户打断的占比
- `successRate`
  - 终态会话中，最终通过检查并完成的占比

## 6. 运维约束

- SQLite 可用于本地开发
- PostgreSQL 用于长期运行环境
- 使用 `backend/scripts/reset_lite_core_schema.py` 做破坏式 schema reset
- 历史模块表不再保留
