# Operator Control Plane Runbook

这份 runbook 面向外部操作者，而不是开发实现者。

目标只有 5 个问题：

1. 现在系统状态怎么样
2. 卡在哪里
3. 怎样重新触发
4. 怎样打断
5. 怎样重启

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
pwsh -File .\kam-operator.ps1 status
pwsh -File .\kam-operator.ps1 watch --interval-seconds 5
pwsh -File .\kam-operator.ps1 status --json
pwsh -File .\kam-operator.ps1 status --fail-on-attention
```

说明：

- `status`：拉一次 operator control plane，并输出简洁摘要
- `watch`：持续轮询，适合值班时盯盘
- `--json`：输出原始 JSON，适合集成到外部脚本
- `--fail-on-attention`：当系统进入 `attention` 时返回退出码 `2`

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
pwsh -File .\kam-operator.ps1 continue --task-id task-harness-cutover
pwsh -File .\kam-operator.ps1 retry --run-id task-run-123
pwsh -File .\kam-operator.ps1 adopt --run-id task-run-123
```

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
pwsh -File .\kam-operator.ps1 stop-scope --task-id task-harness-cutover
pwsh -File .\kam-operator.ps1 cancel --task-id task-harness-cutover --run-id task-run-123
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
