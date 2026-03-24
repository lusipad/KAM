# AI工作助手 Lite MVP Backlog

## 目标

在 2 到 4 周内交付一个可自用的“外置大脑 + Agent 指挥台”最小版本，满足以下主链路：

1. 记录任务和上下文
2. 为任务绑定工作项、仓库、文档和笔记引用
3. 为任务创建多个 Agent run
4. 统一查看 run 的状态、提示词、日志和产物
5. 对结果进行人工收口

## 范围切片

### Slice 1: 任务台基础
- [x] 明确 Lite 架构与文档方向
- [x] 任务卡数据模型
- [x] 任务列表 / 创建 / 更新 / 归档 API
- [x] 前端任务列表与详情面板

### Slice 2: 上下文与引用
- [x] 任务引用数据模型
- [x] 支持工作项、仓库、文件、URL 等引用
- [x] 生成上下文快照
- [x] 在任务详情里查看上下文摘要

### Slice 3: Agent Run 管理
- [x] Agent run 数据模型
- [x] 创建 run、查看 run、取消 run、重试 run API
- [x] prompt/context artifact 落库
- [x] 前端 run 列表与状态展示

### Slice 4: 结果收口
- [x] run artifact 数据模型
- [x] review 汇总接口
- [x] 任务维度结果收口页
- [ ] 风险项与下一步建议摘要

### Slice 5: 真正执行器接入
- [x] Codex CLI adapter
- [x] Claude Code CLI adapter
- [ ] worktree 生命周期管理
- [x] run 日志和退出码追踪
- [x] git changes / patch artifact 采集
- [x] artifact tail 轮询接口

## 本轮执行

当前已经完成 Slice 1 到 Slice 4 的主链路，以及 Slice 5 的第一版真实执行：

- Lite 任务域模型已落地
- 任务 / 上下文 / run / review API 已落地
- 前端任务台已可创建任务、绑定引用、创建 runs、查看 artifacts
- 真实 `Codex / Claude Code / custom command` 执行已接入
- `git changes / patch` artifacts 已接入
- 运行中 stdout/stderr 已支持 tail 轮询
- 旧知识管理 / ClawTeam / ADO 页面继续保留

## 暂不处理

- 复杂权限系统
- 审批流
- 向量检索默认启用
- 企业级多用户协作
- 自动写回 ADO
- Agent 自治协商
