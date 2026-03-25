# Optimization Campaign

## 目标

优化战役不是再造一套新系统，而是用当前已经做好的自治闭环去跑一轮真实样本。

核心做三件事：

- 自动建任务
- 自动拉起自治会话
- 自动汇总达成率、打断率、成功率和失败模式

## 运行前提

确保本地后端已经启动：

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

建议运行前确认：

- 根目录 `.venv` 可用
- `app/node_modules` 已安装
- 本地 `codex` 可执行

## 运行方式

```bash
cd backend
py scripts/run_optimization_campaign.py --limit 10
```

## 默认行为

脚本会：

1. 创建 10 个优化任务
2. 给每个任务绑定 `repo-path` 与相关文件引用
3. 用自治会话逐个执行
4. 默认使用 `codex exec --model gpt-5.4 -c model_reasoning_effort="low"`
5. 为每个任务创建隔离 `git worktree`
6. 在当前 worktree 上执行统一检查：
   - `App lint`
   - `App build`
   - `App e2e`
   - `Backend unit`
7. 如果前几轮失败，会把失败检查与失败摘要压缩成新的 `strategy notes`，加入后续任务目标

## 输出位置

输出写到：

```text
storage/campaigns/<campaign-id>/
  report.json
  report.md
```

## 报告字段

- `totalTasks`
  样本总数
- `completedTasks`
  最终完成的任务数
- `failedTasks`
  最终失败的任务数
- `interruptedTasks`
  被显式打断的任务数
- `autonomyCompletionRate`
  不打断且完成的占比
- `interruptionRate`
  被打断的占比
- `successRate`
  最终完成的占比
- `averageIterations`
  每个样本平均使用的轮次
- `topFailedChecks`
  最常见失败检查项

## 如何解释结果

- `autonomyCompletionRate` 高，说明系统能自己把任务推进到终态
- `successRate` 高但 `autonomyCompletionRate` 低，说明系统能做成，但仍然依赖人工中途介入
- `interruptionRate` 升高，说明默认自治行为偏离预期
- `topFailedChecks` 长期集中在同一项，说明先该修系统，不该继续扩样本

## 迭代方式

建议按下面顺序优化：

1. 先修运行环境与检查链路
2. 再修 prompt、策略提示和任务拆分
3. 最后扩大战役规模或延长运行时间

## 参考结果

已实跑结果见：

- [Autonomy Optimization Report 2026-03-25](campaigns/2026-03-25-autonomy-optimization-report.md)
