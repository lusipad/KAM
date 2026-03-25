# Optimization Campaign

## 目标

这份脚本不是再造一套新系统，而是用当前已经做好的自治闭环去跑一轮真实样本。

核心做三件事：

- 自动建任务
- 自动拉起自治会话
- 自动汇总达成率、打断率、成功率

## 运行方式

确保本地后端已经启动：

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

然后执行：

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
5. 对每个任务执行统一检查：
   - `app` lint
   - `app` build
   - `app` e2e
   - `backend` unit tests
6. 如果前几轮失败，会把失败检查与失败摘要压缩成新的策略提示，加到后续任务目标里

## 报告位置

输出写到：

```text
storage/campaigns/<campaign-id>/
  report.json
  report.md
```

## 如何看结果

- `autonomyCompletionRate`
  表示任务样本里有多少在不中断的情况下完成
- `interruptionRate`
  表示样本里有多少被中途打断
- `successRate`
  表示终态样本里有多少最终通过检查
- `topFailedChecks`
  表示当前系统最容易卡住的检查项

## 使用建议

- 如果 `topFailedChecks` 反复集中在同一个检查项，先优化 prompt / 策略提示，再继续扩大战役规模
- 如果 `interruptionRate` 上升，说明自治链路的默认行为开始偏离预期，需要先收敛边界
- 如果 `successRate` 高但 `autonomyCompletionRate` 低，说明系统能做成，但仍然太依赖人工中途介入
