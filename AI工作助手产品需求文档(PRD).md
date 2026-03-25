# KAM Lite 产品需求文档

## 1. 产品目标

KAM Lite 的唯一目标，是把开发任务从脑内和聊天窗口里漂浮的描述，变成可执行、可追踪、可检查、可自治迭代的工作单元。

它不是知识平台，也不是治理平台。它只保留下面这条主链路：

`TaskCard -> TaskRef -> ContextSnapshot -> AgentRun -> Review / Compare -> AutonomySession`

## 2. 目标用户

- 个人开发者：需要管理多个 Agent 输出，避免上下文丢失
- 小团队成员：需要把工单、仓库路径、文档链接快速挂到任务上
- 技术负责人：需要对多个 Agent 结果做并行对比，并衡量自治完成情况

## 3. 核心价值

- 任务外置化：把任务、目标、约束、链接收进任务卡
- 上下文收敛：把当前任务需要的引用和历史运行结果打包成快照
- 并发执行：同一任务可以拉起多个 `AgentRun`
- 结果收口：在一个任务维度看日志、`summary`、`changes`、`patch` 和 `compare`
- 自治验收：让 AI 不只“生成一次答案”，而是持续迭代直到通过检查

## 4. 范围内

### 4.1 任务与引用

- 创建、更新、归档任务卡
- 设置任务标题、描述、状态、优先级、标签
- 为任务添加 URL、仓库路径、文件路径、工单号、PR、文档链接等引用

### 4.2 上下文快照

- 仅聚合三类数据：
  - 当前任务信息
  - 任务引用
  - 最近运行记录
- 不再自动拼接额外历史上下文来源

### 4.3 Agent Runs

- 支持 `codex`
- 支持 `claude-code`
- 支持 `custom command`
- 支持独立运行目录与 `git worktree`
- 支持查看 `prompt / context / plan / stdout / stderr / summary / changes / patch`

### 4.4 Review / Compare

- 任务维度 `review summary`
- run 维度 `compare`
- 人工判断是否采纳、重试、继续追问

### 4.5 自治闭环

- 创建 `AutonomySession`
- 在会话中持续生成 `AutonomyCycle`
- 每轮执行后自动运行检查命令
- 记录打断、失败、完成与失败反馈
- 聚合任务级与全局自治指标

### 4.6 Dogfooding 与战役

- 内置 `KAM Dogfood` 模板
- 支持批量创建优化任务并跑 10 任务样本
- 输出战役报告，作为后续优化输入

## 5. 明确不做

- 额外独立工作台或管理台
- 旧 API 兼容层
- 平台内 patch apply
- 旧表保留与旧数据迁移
- 独立连接器管理页面

## 6. 核心指标

- `autonomyCompletionRate`
  回答 AI 是否能在不中断用户的前提下自己做完
- `interruptionRate`
  回答用户是否经常需要中途介入、暂停或重定向
- `successRate`
  回答最终结束的会话里，有多少是真的通过检查并完成

这些指标的精确定义以 `docs/autonomy-v2.md` 与 `docs/documentation-standards.md` 为准。

## 7. 核心接口

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
- `GET/POST /api/tasks/{task_id}/autonomy/sessions`
- `POST /api/tasks/{task_id}/autonomy/dogfood`
- `GET /api/tasks/{task_id}/autonomy/metrics`
- `GET /api/autonomy/metrics`

## 8. 验收标准

- 首屏只有一个任务工作台，不再出现旧模块导航
- 创建任务、添加引用、生成快照、创建 run、查看 artifacts、`compare` 全链路可用
- 可以创建自治会话并看到每轮检查结果与失败反馈
- 可以看到任务级与全局的自主完成率、打断率、完成成功率
- 后端只暴露 Lite Core 与自治 API
- 数据库只保留 Lite Core 与自治表
- 根文档只描述当前系统；历史文档移入 `docs/archive/legacy/`
