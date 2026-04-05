# KAM Harness 产品需求文档

## 1. 产品定义

KAM 当前的唯一目标，不再是做 conversation-first workspace，而是做一个 `local-first`、`task-first`、`dogfood-first` 的软件工程 harness。

它的主链路是：

`Task -> Refs -> Context Snapshot -> Runs -> Artifacts -> Review / Compare -> Follow-up Planning -> Next-Task Dispatch`

第一用户不是抽象团队，而是当前仓库自身：`KAM builds KAM`。

## 2. 目标用户

- 第一用户：当前开发者本人
- 第一仓库：`D:\Repos\KAM`
- 扩展用户：需要管理多个 agent 输出、并把工作拆解和收口显式化的个人开发者或小团队

## 3. 核心价值

- 任务外置化：把目标、边界、仓库路径和引用从聊天上下文中抽离出来
- 上下文收敛：把 `Task + Refs + Snapshot + Run Artifacts` 收敛成当前可执行上下文
- 结果可比对：同一任务下可以直接比较多轮 run 的差异与结论
- 后续工作显式化：根据当前 task / run / compare 自动拆出可执行 child task
- 连续推进：KAM 不只会拆任务，还能自己从任务池里接下一张并启动 run

## 4. 保留功能

### 4.1 Task Workbench

- 创建、更新、归档任务
- 设置任务标题、描述、仓库路径、状态、优先级、标签
- 查看任务 refs、snapshots、runs、artifacts、compare
- 在同一个工作台里完成收集上下文、运行、比较、收口

### 4.2 Refs

- 为任务添加文件路径、仓库路径、文档链接、工单号、PR 等引用
- 引用只作为任务上下文输入，不单独衍生为一个新的产品面
- planner 创建 child task 时可自动带入建议 refs

### 4.3 Context Snapshot

- 将当前任务信息和 refs 收敛为可执行上下文
- 允许带 `focus`
- run 启动时可自动补当前 snapshot

### 4.4 Agent Runs

- 当前支持 `codex`
- 当前支持 `claude-code`
- 支持本地 `git worktree` 执行
- 支持查看 `task_snapshot / context_snapshot / stdout / summary / changed_files / patch`
- 支持 `retry`
- 对通过的 run 支持 `adopt`

### 4.5 Review / Compare

- 基于任务维度查看 compare 结果
- 基于两个 run 生成 summary
- 为后续 planning 和 dispatch 提供显式输入

### 4.6 Task Self-Planning

- 基于当前 `Task / Run / Compare / Snapshot / Refs / Artifacts` 自动生成 1-N 个 follow-up suggestions
- 支持直接创建 child task
- child task 自动带上：
  - `recommendedPrompt`
  - `recommendedAgent`
  - `acceptanceChecks`
  - `suggestedRefs`

### 4.7 Task Self-Dispatch

- KAM 可以从现有任务池中挑选下一张带推荐 Prompt 的任务
- 如果当前没有可跑 child task，可以先从父任务自动拆一张，再立即发起 run
- next-task dispatch 必须复用同一条 `Task -> Snapshot -> Run` 主链路，不允许形成平行执行系统

## 5. 非目标

- 不恢复 Home / Watchers / Memory 作为主产品能力
- 不先做 SaaS、多租户、账号体系
- 不先做重型队列系统、claim 服务或调度中心
- 不先做大量连接器
- 不为了历史兼容保留 V3 双主线
- 不引入额外 planner 专用持久化表，除非现有 metadata 已无法承载

## 6. 核心接口

### 6.1 Tasks

- `GET /api/tasks`
- `POST /api/tasks`
- `GET /api/tasks/{task_id}`
- `PATCH /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/archive`

### 6.2 Refs / Context

- `POST /api/tasks/{task_id}/refs`
- `DELETE /api/tasks/{task_id}/refs/{ref_id}`
- `POST /api/tasks/{task_id}/context/resolve`
- `GET /api/context/snapshots/{snapshot_id}`

### 6.3 Runs / Artifacts

- `POST /api/tasks/{task_id}/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/artifacts`
- `POST /api/runs/{run_id}/retry`
- `POST /api/runs/{run_id}/adopt`

### 6.4 Compare / Planning / Dispatch

- `POST /api/reviews/{task_id}/compare`
- `POST /api/tasks/{task_id}/plan`
- `POST /api/tasks/dispatch-next`

### 6.5 Dev Support

- `POST /api/dev/seed-harness`

## 7. 当前默认行为

- 默认 agent 是 `codex`
- `claude-code` 保留为可选执行目标和额外 smoke 目标
- 本地默认门禁是：

```powershell
pwsh -NoProfile -File .\verify-local.ps1
```

## 8. 验收标准

- 默认入口只有 task-first workbench，不再出现 V3 主入口
- 能创建任务、添加 refs、生成 snapshot、发起 run、查看 artifacts、创建 compare
- 能从当前任务自动拆出可执行 child task
- 能从任务池里自动接下一张任务；必要时先拆后跑
- `verify-local.ps1` 持续为绿
- 根文档和主产品文档必须与当前真实主链路一致
