# KAM V3 本地交付状态

> 当前默认目标是“本地优先工作台”，不是“零改造云原生 SaaS”。
> 本文档只描述当前主线状态和剩余缺口，不重复历史 phase 计划。

---

## 当前判断

- 产品主线完成度：约 90% - 95%
- 本地交付完成度：约 95%
- 云部署完成度：约 60% - 75%

当前仓库已经完成 V3 的核心产品闭环，重点剩余项主要集中在部署形态与工程化收口，而不是主功能缺失。

## 已完成主线

- 三栏工作台：Sidebar / Main / Memory panel
- Home feed：需要关注、运行中、最近历史三层优先级
- Thread 对话流：消息、Run 卡片、草稿监控卡片、失败态与采纳闭环
- Memory：偏好、决策、经验、项目上下文查看
- Watchers：创建草稿、启用、暂停、恢复、立即执行、事件处理
- 后端主线：`/api/*`、bootstrap、SSE、SQLite、Alembic baseline
- 本地脚本：`start-local.*`、`verify-local.ps1`、`seed-demo.ps1`
- 本地验证：后端单测、前端 lint/build、浏览器 smoke

## 当前仍有缺口

### 本地形态内的收尾项

- 文档口径继续统一，减少 v2 / v3 混用痕迹
- 异常恢复说明、CLI 缺失时的诊断说明继续打磨
- 针对中文文案、移动端断点、异常状态再做少量走查

### 云部署相关缺口

- 当前运行引擎依赖本地 `codex` / `claude-code` CLI
- Run 依赖本地 `git worktree`、子进程执行和自动 commit
- Watcher 依赖常驻 scheduler
- 持久化默认基于本地 SQLite 与本地文件目录

这意味着当前 V3 适合本地机器、常驻开发机或完整 Linux 主机，不适合直接当作无状态 Web 应用部署到展示型免费平台。

## 当前建议

- 如果目标是“先把产品做成可用工具”，继续坚持本地优先
- 如果下一步要上线，优先选择 Linux VPS / 云主机，再考虑 PaaS
- 如果只是做公开演示，再补一个 demo mode，而不是直接迁完整后端

## 对应文档

- 架构设计：[../design/v3_architecture_design.md](../design/v3_architecture_design.md)
- UI 规范：[../design/v3_ui_spec.md](../design/v3_ui_spec.md)
- 历史 phase 路线图：[./v2_implementation_roadmap.md](./v2_implementation_roadmap.md)
