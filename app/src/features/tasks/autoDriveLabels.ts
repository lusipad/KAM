export function autoDriveStatusLabel(value: string | null) {
  if (value === 'running') {
    return '执行中'
  }
  if (value === 'waiting_for_lease') {
    return '等待 lease'
  }
  if (value === 'waiting_for_run') {
    return '等待 run'
  }
  if (value === 'idle') {
    return '已停机'
  }
  if (value === 'disabled') {
    return '已关闭'
  }
  if (value === 'paused') {
    return '已暂停'
  }
  if (value === 'error') {
    return '异常'
  }
  return value
}

export function autoDriveActionLabel(value: string | null) {
  if (value === 'adopt') {
    return '采纳'
  }
  if (value === 'retry') {
    return '重试'
  }
  if (value === 'plan_and_dispatch') {
    return '拆并跑'
  }
  if (value === 'stop') {
    return '停止'
  }
  return value
}

export function autoDriveReasonLabel(value: string | null) {
  if (value === 'latest_passed_run_adopted') {
    return '已采纳最近通过 run'
  }
  if (value === 'latest_failed_run_retried' || value === 'latest_failed_child_run_retried') {
    return '已重试最近失败 run'
  }
  if (value === 'dispatched_next_runnable_task') {
    return '已挑出下一张可跑任务'
  }
  if (value === 'scope_task_terminal') {
    return '当前任务已收口'
  }
  if (value === 'scope_has_active_run') {
    return '当前仍有 run 在执行'
  }
  if (value === 'latest_failed_run_retry_budget_exhausted') {
    return '最近失败 run 已到自动重试上限'
  }
  if (value === 'no_high_value_action') {
    return '当前没有更高价值的下一步'
  }
  if (value === 'adopt_failed') {
    return '自动采纳失败'
  }
  if (value === 'global_auto_drive_lease_held_by_other_process') {
    return '另一实例正在持有全局 lease'
  }
  if (value === 'global_auto_drive_error') {
    return '调度异常，系统会自动重试'
  }
  if (value === 'global_auto_drive_dispatch_timeout') {
    return '全局无人值守单步调度超时，系统会自动重试'
  }
  if (value === 'auto_drive_dispatch_timeout') {
    return '当前任务族单步调度超时'
  }
  if (value === 'global_auto_drive_restarting') {
    return 'supervisor 中断后正在自动重启'
  }
  if (value === 'global_auto_drive_stopped') {
    return '已手动停止全局无人值守'
  }
  if (value === 'global_auto_drive_step_limit_reached') {
    return '达到单轮步数上限'
  }
  return value
}
