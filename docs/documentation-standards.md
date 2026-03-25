# Documentation Standards

## 目标

这份规范只做三件事：

- 固定术语口径
- 固定文档分工
- 固定文档内容结构

目标不是把文档写得更花，而是让产品、架构、自治、战役和报告不再互相打架。

## 文档分工

| 文档 | 唯一职责 | 不应该承载什么 |
| --- | --- | --- |
| `README.md` | 仓库入口、边界、启动方式、文档导航 | 详细设计推导 |
| `AI工作助手产品需求文档(PRD).md` | 产品目标、范围、验收标准 | 底层实现细节 |
| `system_architecture.md` | 系统结构、数据模型、运行路径 | 需求优先级讨论 |
| `docs/autonomy-v2.md` | 自治闭环设计、状态机、指标口径、操作手册 | 通用产品介绍 |
| `docs/optimization-campaign.md` | 战役脚本、样本运行方式、结果解释 | 长篇复盘结论 |
| `docs/campaigns/*.md` | 某次实跑战役的结论与数据 | 未来规划总表 |
| `MVP_BACKLOG.md` | 当前与下一轮优先级 | 已完成事实记录 |

## 术语规范

以下术语必须统一使用，不要在同一份文档里混用多个叫法：

| 中文 | 代码标识 | 说明 |
| --- | --- | --- |
| 任务卡 | `TaskCard` | 开发任务的基本单元 |
| 引用 | `TaskRef` | 仓库路径、文件、URL、工单、PR 等输入 |
| 上下文快照 | `ContextSnapshot` | `{ task, refs, recentRuns }` 的聚合结果 |
| 运行 | `AgentRun` | 单次 Agent 执行记录 |
| 运行产物 | `RunArtifact` | `prompt / context / stdout / stderr / summary / changes / patch` |
| 自治会话 | `AutonomySession` | 一次持续迭代的自治任务 |
| 自治轮次 | `AutonomyCycle` | 自治会话中的单轮执行与检查 |
| 自主完成率 | `autonomyCompletionRate` | `completed 且 interruption_count == 0` / 全部终态会话 |
| 打断率 | `interruptionRate` | `interrupted` / 全部终态会话 |
| 完成成功率 | `successRate` | `completed` / 全部终态会话 |
| 高频失败检查 | `topFailedChecks` | 终态会话里最常见的失败检查标签 |
| Dogfooding / KAM Dogfood | `KAM Dogfood` | 用 KAM 自己开发 KAM 的内置模板 |

补充规则：

- “成功率”单独出现时，默认指 `successRate`
- “完成率”单独出现时，必须写清是 `autonomyCompletionRate` 还是 `successRate`
- “打断”只指用户显式中断，不包含检查失败、异常退出或达到最大轮次

## 指标口径规范

所有文档里关于指标的描述都必须满足下面几点：

1. 统一分母是终态会话：`status in {completed, failed, interrupted}`
2. `autonomyCompletionRate` 必须被描述为 `successRate` 的子集
3. `interruptionRate` 只统计显式打断
4. `topFailedChecks` 必须说明是“失败检查项频次”，不是最终失败任务列表

## 内容结构规范

### README

至少包含：

- 产品定位
- 核心工作链路
- 核心指标
- 系统边界
- 启动方式
- 文档导航

### PRD

至少包含：

- 产品目标
- 目标用户
- 核心价值
- 范围内
- 明确不做
- 核心指标
- 验收标准

### Architecture

至少包含：

- 架构目标
- 组件关系
- 数据模型
- 关键运行路径
- 自治与检查执行方式
- 指标来源
- 运维约束

### Autonomy

至少包含：

- 自治目标
- 对象模型
- 状态机
- 闭环流程
- 指标口径
- 默认检查
- Operator Playbook

### Campaign Report

至少包含：

- 样本范围
- 结果摘要
- 失败模式
- 关键改动
- 下一轮建议

## 写作规范

- 产品文档讲“为什么”和“做什么”，不要展开底层实现
- 架构文档讲“怎么组织”和“怎么运行”，不要写需求优先级
- 战役报告只记录已经跑出来的事实，不把假设写成结论
- 指标要给绝对样本量，不只写百分比
- 结论引用相对日期时，尽量附带绝对日期
- 新增文档文件名默认使用 ASCII；历史文件名可保留

## 更新规范

以下改动发生时，必须同步更新对应文档：

- 改 API、模型、检查链路：更新 `system_architecture.md`
- 改自治循环、指标、dogfood、战役：更新 `docs/autonomy-v2.md` 或 `docs/optimization-campaign.md`
- 改产品边界或范围：更新 PRD 与 README
- 根据实跑结果调整路线：更新 `docs/campaigns/*.md` 与 `MVP_BACKLOG.md`

## 文档检查清单

提交前至少反查以下问题：

- 同一概念是否用了多个名字
- 指标口径是否和系统实现一致
- 文档职责是否混乱
- 结论是否来自真实结果而不是猜测
- README 的文档导航是否已更新
