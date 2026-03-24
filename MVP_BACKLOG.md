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
- [ ] 任务卡数据模型
- [ ] 任务列表 / 创建 / 更新 / 归档 API
- [ ] 前端任务列表与详情面板

### Slice 2: 上下文与引用
- [ ] 任务引用数据模型
- [ ] 支持工作项、仓库、文件、URL 等引用
- [ ] 生成上下文快照
- [ ] 在任务详情里查看上下文摘要

### Slice 3: Agent Run 管理
- [ ] Agent run 数据模型
- [ ] 创建 run、查看 run、取消 run、重试 run API
- [ ] prompt/context artifact 落库
- [ ] 前端 run 列表与状态展示

### Slice 4: 结果收口
- [ ] run artifact 数据模型
- [ ] review 汇总接口
- [ ] 任务维度结果收口页
- [ ] 风险项与下一步建议摘要

### Slice 5: 真正执行器接入
- [ ] Codex CLI adapter
- [ ] Claude Code CLI adapter
- [ ] worktree 生命周期管理
- [ ] run 日志和退出码追踪

## 本轮执行

本轮优先交付 Slice 1 到 Slice 3 的基础骨架：

- 新增 Lite 任务域的数据模型
- 新增任务 / 上下文 / run / review API
- 新增前端任务台入口
- 保持旧知识管理 / ClawTeam / ADO 页面可继续使用

## 暂不处理

- 复杂权限系统
- 审批流
- 向量检索默认启用
- 企业级多用户协作
- 自动写回 ADO
- Agent 自治协商
