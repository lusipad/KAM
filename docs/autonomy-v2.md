# KAM Autonomy V2

## 目标

自治的核心不是“再多一个工作台”，而是让 AI 能持续、反复地把同一个任务推进到可验收状态。

判断标准只有三组：

- 自主完成率
- 打断率
- 完成成功率

## 设计原则

- 自治不是单次 run，而是一个 `Session -> Cycle -> Check` 的闭环
- 完成必须以检查通过为准，不能只看模型输出“说自己完成了”
- 打断必须被明确记录，不能混在失败态里
- `KAM Dogfood` 不是附加玩法，而是默认验证路径

## 对象模型

### `AutonomySession`

表示一次自治任务，保存：

- 绑定任务
- 主 Agent
- 最大迭代次数
- 成功标准
- 检查命令
- 打断次数
- 最终状态

### `AutonomyCycle`

表示自治会话中的一轮迭代，保存：

- 第几轮
- 对应的 worker run
- 检查结果
- 失败反馈
- 本轮状态

## 状态机

### 会话状态

- `draft`
- `running`
- `completed`
- `failed`
- `interrupted`

### 轮次状态

- `running`
- `checking`
- `passed`
- `failed`
- `interrupted`

规则：

- `interrupted` 只代表用户显式中断
- 达到最大轮次仍未通过检查，记为 `failed`
- 只有 worker run 完成且检查全部通过，才记为 `completed`

## 闭环流程

1. 选中一个任务，创建自治会话
2. 系统生成上下文，并拉起 worker run
3. worker run 结束后，执行检查命令
4. 如果检查通过，会话记为 `completed`
5. 如果检查失败，系统把失败反馈拼进下一轮 `prompt appendix`
6. 如果用户手动打断，会话记为 `interrupted`
7. 如果达到最大轮次仍未通过，会话记为 `failed`

## 指标口径

统一分母：

- 全部终态会话
- 即 `status in {completed, failed, interrupted}`

### 自主完成率

`completed 且 interruption_count == 0` / 全部终态会话

回答的问题：

- AI 是否能在不中断用户的前提下自己做完

### 打断率

`interrupted` / 全部终态会话

回答的问题：

- 用户是否经常需要中途介入、暂停、重定向

### 完成成功率

`completed` / 全部终态会话

回答的问题：

- 一旦会话结束，最终有多少是真的把工作做成了

### 高频失败检查

`topFailedChecks` 统计终态会话里 `passed = false` 的检查标签频次。

回答的问题：

- 系统最常卡在哪个检查环节

## KAM Dogfood 模板

当前内置了 `KAM Dogfood` 模板，默认绑定本仓库，并自动执行：

- `App lint`
- `App build`
- `App e2e`
- `Backend unit`

默认行为：

- 检查优先在当前自治 `worktree` 上执行
- `Backend unit` 优先使用 `worktree/.venv` 或仓库根目录 `.venv`
- worktree 会自动挂接共享运行时依赖，避免只改代码不带运行环境

## Operator Playbook

### 什么时候跑一轮战役

以下情况默认应该跑一次 10 任务样本：

- 新增或重构自治链路
- 修改检查模板
- 调整默认 prompt / strategy notes
- 调整 worktree、运行时、依赖挂接方式

### 怎么跑

1. 启动本地后端
2. 执行 `py scripts/run_optimization_campaign.py --limit 10`
3. 读取 `storage/campaigns/<campaign-id>/report.json`
4. 对照 `completed / failed / interrupted / topFailedChecks` 做复盘

### 怎么判断结果

- `autonomyCompletionRate >= 0.7`
  说明系统已经具备较强自治能力
- `0.4 <= autonomyCompletionRate < 0.7`
  说明系统可用，但仍有明显环境或策略摩擦
- `autonomyCompletionRate < 0.4`
  说明系统还没形成稳定闭环
- `interruptionRate > 0.2`
  说明默认自治行为开始偏离预期
- `topFailedChecks` 长期集中在同一项
  说明应该先优化系统约束，而不是继续加任务样本

### 如何调优

优先级顺序：

1. 先修环境与检查链路
2. 再修默认 prompt / strategy notes
3. 最后才扩大战役规模

## 已落地能力

- 后端自治会话与自治周期模型
- 自动迭代 manager
- 检查命令执行与结果记录
- 任务级 / 全局指标 API
- 前端自治面板
- 一键 `KAM Dogfood`
- 优化战役脚本

## 下一轮建议

- 给自治会话增加“验收 Agent”，把规则检查和语义检查分开
- 支持会话级策略切换，例如修复优先 / 探索优先
- 把检查结果沉淀成可复用模板
- 提供战役历史趋势，而不是只看单次报告
