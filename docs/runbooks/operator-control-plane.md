# Operator Control Plane Runbook

这份 runbook 面向外部操作者，而不是开发实现者。

目标只有 5 个问题：

1. 现在系统状态怎么样
2. 卡在哪里
3. 怎样重新触发
4. 怎样打断
5. 怎样重启

先给结论：

- 人工值守优先 `pwsh -File .\kam-operator.ps1 menu`
- 持续盯盘优先 `pwsh -File .\kam-operator.ps1 watch --interval-seconds 5`
- 脚本集成优先 `pwsh -File .\kam-operator.ps1 status --json`
- 告警/计划任务优先 `pwsh -File .\kam-operator.ps1 status --fail-on-attention`

## 入口

- UI：顶部 `操作台`
- CLI：`pwsh -File .\kam-operator.ps1 ...`
- API：
  - `GET /api/operator/control-plane`
  - `POST /api/operator/actions`

UI 的 `操作台` 内也会直接显示一组“值守说明”，把状态查看、重新触发、打断、重启这 4 类动作收成同一个入口。

如果你在 UI 里已经选中某张任务，`操作台` 会自动把当前焦点落到这张 task family。
如果你走 API，也可以通过 `task_id` 把 control plane 对齐到某个 task family：

```http
GET /api/operator/control-plane?task_id=task-harness-cutover
```

如果你在终端值守，最常用的是：

```powershell
pwsh -File .\kam-operator.ps1 menu
pwsh -File .\kam-operator.ps1 status
pwsh -File .\kam-operator.ps1 watch --interval-seconds 5
pwsh -File .\kam-operator.ps1 status --json
pwsh -File .\kam-operator.ps1 status --fail-on-attention
```

说明：

- `menu`：给本机人工值守用的轻交互入口，只显示当前状态和 control plane 已推荐动作
- `status`：拉一次 operator control plane，并输出简洁摘要
- `watch`：持续轮询，适合值班时盯盘
- `--json`：输出原始 JSON，适合集成到外部脚本
- `--fail-on-attention`：当系统进入 `attention` 时返回退出码 `2`

CLI 还有一个约定：

- `continue / start-scope / stop-scope` 在未传 `--task-id` 时，会自动复用当前 control plane 的焦点 task
- `adopt / retry / cancel` 在未传 `--run-id` 时，会自动复用当前 control plane 已推荐的 run
- 如果你要绕过当前推荐对象，仍可显式传 `--task-id` / `--run-id`

## 命令怎么选

- 你是人在本机操作：优先 `menu`
- 你只是想看状态，不需要交互：用 `status`
- 你想连续盯盘：用 `watch`
- 你在接外部脚本、调度器、监控：用 `status --json`
- 你在做健康检查或接告警：用 `status --fail-on-attention`

## 系统里的工作怎么和现实对应

不要把 KAM 里的 task 只看成一条内部记录。对真实用户来说，一张 task 至少要和下面 4 类现实对象挂钩：

- 来源
  - 例如 GitHub PR 评论、人工创建的一张任务、某个上游任务拆出来的后继任务
- 真实目标
  - 例如要改哪个仓库、哪个分支、哪个 PR
- 当前执行
  - 当前有没有 run 正在跑，由哪个 agent 在跑
- 当前建议
  - 系统现在推荐你继续、重试、采纳、打断还是重启

你在 UI 或 CLI 里优先看这几项：

- `当前焦点`
  - 它告诉你 KAM 现在盯着哪张 task、哪个 scope、哪个 run
- `现实对应`
  - `来源` 说明这张活从哪里来
  - `目标` 说明结果最终要落到哪里
- `需要关注`
  - 告诉你现在是失败、阻塞、待采纳，还是 supervisor 异常
- `推荐动作` / `可执行动作`
  - 告诉你下一步最合理的人工动作

如果一张 task 是由 GitHub PR review comment monitor 送进来的，你应该能把它理解成：

- 来源：`某个 repo 的某个 PR 评论`
- 目标：`对应 head branch`
- 成功结果：`修复后的 commit 被推回该分支`

如果一张 task 没有远端执行目标，它通常就是：

- 来源：`KAM 本地任务池`
- 目标：`当前本地 repoPath`

正常使用时，你不需要关心 `lease / autodrive / control plane` 的内部实现细节；你只需要确认“这张活来自哪里、将落到哪里、现在建议我做什么”。

## 怎么看状态

先看 `总状态`：

- `执行中`：当前有 run 正在执行
- `待介入`：有失败、阻塞、待采纳结果，或者全局 supervisor 报错
- `可推进`：没有明显故障，但有任务可继续
- `空闲`：当前没有立即要处理的动作

再看 4 个信号：

- `全局`：是否开启跨 task family 的无人值守
- `Running / Blocked / Failed / 待采纳`：当前积压结构
- `当前焦点`：系统现在盯着哪张任务、哪个 scope、哪个 run
- `最近事件`：最近一次等待、失败、重启、接单、切换原因

如果你想知道“系统里的状态怎么映射成现实动作”，可以这样理解：

- `执行中`
  - 现实含义：有一个 agent run 正在真正执行
- `待介入`
  - 现实含义：现在需要你看一眼并做决定，通常是失败、阻塞、待采纳或 supervisor 异常
- `可推进`
  - 现实含义：系统没坏，当前有明确下一步可以继续
- `空闲`
  - 现实含义：当前没有 run 在跑，也没有立刻要处理的高优先级动作

## 怎么重新触发

常见的重新触发入口：

- `让 KAM 接下一张`
  - 作用：从全局任务池里挑下一张高价值任务，必要时先拆再跑
  - 适用：你想恢复全局推进，但不限定某个 family
- `继续推进当前任务`
  - 作用：只围绕当前 task family 判断 `adopt / retry / plan / dispatch`
  - 适用：你只想让某个任务族继续闭环
- `重试最近失败 Run`
  - 作用：重新跑最近失败且仍有预算的 run
  - 适用：失败原因已经明确，想直接再跑一轮
- `采纳最近结果`
  - 作用：把最近通过且可采纳的 run 收口回主工作区
  - 适用：结果已通过，希望继续向下游推进

对应 CLI：

```powershell
pwsh -File .\kam-operator.ps1 dispatch
pwsh -File .\kam-operator.ps1 continue
pwsh -File .\kam-operator.ps1 retry
pwsh -File .\kam-operator.ps1 adopt
```

## 重启后会发生什么

先说结论：

- 重启不会续跑已经中断的 agent 进程
- 重启不会清掉 task、refs、snapshot、artifacts、review 这些业务数据
- 重启恢复时，原来停在 `pending / running` 的 run 会被标记成 `failed`
- 如果全局无人值守此前就是开启的，系统会尝试恢复 supervisor
- 如果 lease 还被别的实例持有，系统不会抢跑，而会进入等待状态

所以，“重启”在 KAM 里的真实语义不是“从断点继续跑同一个进程”，而是：

1. 把中断前没完成的 run 明确标成失败
2. 恢复全局无人值守配置和最近状态
3. 重新接管调度
4. 然后由你根据推荐动作决定是 `retry / continue / dispatch / restart`

这也是为什么重启后你常看到的不是“继续当前 run”，而是：

- `重试最近失败 Run`
- `继续推进当前任务`
- `让 KAM 接下一张`
- `重启全局 supervisor`

## 重启后状态怎么体现

重启以后，重点看这 6 个位置：

- `总状态`
  - 如果恢复后发现失败、阻塞、待采纳，通常会变成 `待介入`
  - 如果恢复后能继续推进，通常会变成 `可推进`
- `当前焦点`
  - 看恢复后系统现在重新盯上了哪张任务
- `需要关注`
  - 这里会直接说明是 `failed_run / retry_budget_exhausted / blocked_task / global_error`
- `最近事件`
  - 看有没有新的恢复、等待 lease、异常、重启记录
- `Lease`
  - 看当前实例是否重新持有全局调度 lease
- `可执行动作`
  - 看系统现在建议你做的是 `retry / continue / restart / adopt / cancel` 哪一种

重启后最常见的几种状态是：

- `待介入 + 最近失败`
  - 说明中断前的 run 已被恢复逻辑标成失败，现在等你决定是否重试
- `待介入 + 全局无人值守异常`
  - 说明 supervisor 曾经报错，你需要看最近事件，必要时手动重启
- `等待 lease`
  - 说明另一实例还持有全局调度权，这时不要误以为系统卡死
- `可推进`
  - 说明没有严重故障，系统已经恢复到可继续推进状态

## 怎么打断

有两种“打断”，不要混淆：

- `停止全局无人值守` / `停止无人值守`
  - 作用：停止后续自动推进
  - 不会终止已经在跑的 run
- `打断当前 Run`
  - 作用：直接终止当前正在执行的 agent run
  - 结果：该 run 会被标记为 `cancelled`
  - 适用：prompt 明显错误、执行卡死、方向需要立刻改

推荐顺序：

- 只是不想继续自动接活：先停无人值守
- 需要立刻停下当前 agent：直接 `打断当前 Run`

对应 CLI：

```powershell
pwsh -File .\kam-operator.ps1 stop-global
pwsh -File .\kam-operator.ps1 stop-scope
pwsh -File .\kam-operator.ps1 cancel
```

## 怎么重启

如果全局 supervisor 报错、lease 卡住、或你想强制恢复跨 family 调度，使用：

- `重启全局 supervisor`

语义：

- 若全局无人值守已开启：先停，再重新拉起 supervisor
- 若全局无人值守未开启：等价于重新启动全局无人值守

重启后重点检查：

- `全局` 是否回到已开启
- `最近事件` 是否出现新的重启记录
- `Lease` 是否被当前实例重新持有

对应 CLI：

```powershell
pwsh -File .\kam-operator.ps1 restart-global
```

## 什么时候需要人工介入

出现下面任一情况时，不要只是一味点“继续”：

- `retry budget exhausted`
  - 说明：同一任务已经连续失败到预算上限
  - 动作：先看失败原因，再决定是否改 prompt、补 refs、或拆子任务
- 依赖阻塞
  - 说明：当前任务被上游任务挡住
  - 动作：先完成或解除前置依赖
- 可采纳结果长期未采纳
  - 说明：结果已经通过，但主链路没有收口
  - 动作：确认改动后采纳，避免系统长期停在 passed-but-not-adopted
- 全局 supervisor 异常
  - 说明：后台 loop 曾经超时或报错
  - 动作：优先看 `最近事件`，必要时执行 `重启全局 supervisor`

## API 动作示例

继续当前任务族：

```http
POST /api/operator/actions
Content-Type: application/json

{
  "action": "continue_task_family",
  "taskId": "task-harness-cutover"
}
```

打断当前 run：

```http
POST /api/operator/actions
Content-Type: application/json

{
  "action": "cancel_run",
  "taskId": "task-harness-cutover",
  "runId": "task-run-123"
}
```

重启全局 supervisor：

```http
POST /api/operator/actions
Content-Type: application/json

{
  "action": "restart_global_autodrive"
}
```
