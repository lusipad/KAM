# KAM Lite 产品需求文档

## 1. 产品定义

KAM Lite 的唯一目标，是把开发任务从“脑内和聊天窗口里漂浮”变成“可执行、可追踪、可并发、可收口”的工作单元。

它不是知识平台，也不是治理平台。它只保留下面这条主链路：

`任务卡 -> 引用 -> Context Snapshot -> Agent Runs -> Review / Compare`

## 2. 目标用户

- 个人开发者：需要管理多个 Agent 输出，避免上下文丢失
- 小团队成员：需要把工单、仓库路径、文档链接快速挂到任务上
- 技术负责人：需要对多个 Agent 结果做并行对比和人工收口

## 3. 核心价值

- 任务外置化：把任务、目标、约束、链接收进任务卡
- 上下文收敛：把当前任务需要的引用和历史运行结果打包成快照
- 并发执行：同一任务可以拉起多个 Agent run
- 结果收口：在一个任务维度看日志、summary、changes、patch 和 compare

## 4. 保留功能

### 4.1 任务台

- 创建、更新、归档任务卡
- 设置任务标题、描述、状态、优先级、标签
- 查看任务历史 run 与最新 Context Snapshot

### 4.2 引用管理

- 为任务添加 URL、仓库路径、文件路径、工单号、PR、文档链接等引用
- 引用仅作为上下文输入，不在平台内建独立连接器页面

### 4.3 Context Snapshot

- 仅聚合三类数据：
  - 当前任务信息
  - 任务引用
  - 最近运行记录
- 不再自动拼接额外历史上下文来源

### 4.4 Agent Runs

- 支持 `codex`
- 支持 `claude-code`
- 支持 `custom command`
- 支持独立运行目录与 `git worktree`
- 支持查看 `prompt / context / plan / stdout / stderr / summary / changes / patch`

### 4.5 Review / Compare

- 任务维度 review summary
- run 维度 compare
- 人工判断是否采纳、重试、继续追问

## 5. 明确移除

- 额外独立工作台或管理台
- 旧 API 兼容层
- patch apply
- 旧表保留与旧数据迁移

## 6. 核心接口

- `GET/POST /api/tasks`
- `GET/PUT /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/archive`
- `POST /api/tasks/{task_id}/refs`
- `DELETE /api/tasks/{task_id}/refs/{ref_id}`
- `POST /api/tasks/{task_id}/context/resolve`
- `GET /api/context/snapshots/{snapshot_id}`
- `POST /api/tasks/{task_id}/runs`
- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `POST /api/runs/{run_id}/start`
- `POST /api/runs/{run_id}/cancel`
- `POST /api/runs/{run_id}/retry`
- `GET /api/runs/{run_id}/artifacts`
- `GET /api/runs/{run_id}/events`
- `GET /api/reviews/{task_id}`
- `POST /api/reviews/{task_id}/compare`

## 7. 验收标准

- 首屏只有一个任务工作台，不再出现旧模块导航
- 创建任务、添加引用、生成快照、创建 run、查看 artifacts、compare 全链路可用
- 后端只暴露 Lite Core API
- 数据库只保留 Lite Core 表
- 根文档只描述 Lite Core，历史文档移入 `docs/archive/legacy/`
