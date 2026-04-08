import type { OperatorActionKey, OperatorActionRecord, OperatorControlPlaneResponse } from '@/types/harness'

function systemStatusLabel(value: string | null) {
  if (value === 'running') {
    return '正在执行'
  }
  if (value === 'attention') {
    return '需要你介入'
  }
  if (value === 'ready') {
    return '可以继续推进'
  }
  if (value === 'idle') {
    return '当前空闲'
  }
  if (value === 'waiting_for_run') {
    return '等待下一次执行'
  }
  if (value === 'waiting_for_lease') {
    return '正在等另一实例释放控制权'
  }
  if (value === 'paused') {
    return '已暂停'
  }
  return value || '读取中'
}

function systemStatusTone(value: string | null) {
  if (value === 'attention') {
    return 'red'
  }
  if (value === 'running' || value === 'ready') {
    return 'amber'
  }
  if (value === 'idle') {
    return 'green'
  }
  return 'gray'
}

function buttonClassForTone(tone: OperatorActionRecord['tone']) {
  if (tone === 'green') {
    return 'button-primary'
  }
  if (tone === 'red') {
    return 'button-danger'
  }
  return 'button-secondary'
}

function actionBusyLabel(action: OperatorActionKey) {
  if (action === 'dispatch_next') {
    return '接手中…'
  }
  if (action === 'continue_task_family') {
    return '推进中…'
  }
  if (action === 'start_global_autodrive' || action === 'start_task_autodrive') {
    return '启动中…'
  }
  if (action === 'stop_global_autodrive' || action === 'stop_task_autodrive') {
    return '停止中…'
  }
  if (action === 'restart_global_autodrive') {
    return '重启中…'
  }
  if (action === 'adopt_run') {
    return '采纳中…'
  }
  if (action === 'retry_run') {
    return '重试中…'
  }
  if (action === 'cancel_run') {
    return '打断中…'
  }
  return '处理中…'
}

function summaryHeadline(controlPlane: OperatorControlPlaneResponse | null, tasksCount: number) {
  const focusTask = controlPlane?.focus.task ?? controlPlane?.focus.scopeTask ?? null
  const taskTitle = focusTask?.title ?? '当前系统'

  if (!controlPlane) {
    return '正在读取 KAM 当前状态。'
  }

  if (controlPlane.systemStatus === 'running') {
    return `KAM 正在推进「${taskTitle}」`
  }
  if (controlPlane.systemStatus === 'attention') {
    return `KAM 在「${taskTitle}」这里卡住了，需要你介入`
  }
  if (controlPlane.systemStatus === 'ready') {
    return `KAM 已经准备好继续推进「${taskTitle}」`
  }
  if (controlPlane.systemStatus === 'idle' && tasksCount === 0) {
    return '现在系统里还没有任务'
  }
  if (controlPlane.systemStatus === 'idle') {
    return '现在没有正在自动推进的任务'
  }
  if (controlPlane.systemStatus === 'waiting_for_lease') {
    return '当前实例正在等待接管控制权'
  }
  return controlPlane.systemSummary || 'KAM 当前没有明确的进行中动作。'
}

function summaryDetail(controlPlane: OperatorControlPlaneResponse | null, tasksCount: number) {
  const focusTask = controlPlane?.focus.task ?? controlPlane?.focus.scopeTask ?? null
  const preferredAction = controlPlane?.actions.find((action) => !action.disabled) ?? null
  const attentionItem = controlPlane?.attention[0] ?? null
  const activeRun = controlPlane?.focus.activeRun ?? null

  if (!controlPlane) {
    return '稍等几秒，系统会把当前状态和推荐动作读出来。'
  }

  if (controlPlane.systemStatus === 'running') {
    if (activeRun) {
      return `${activeRun.agent} 正在执行 run。通常现在不用操作；如果你只是想知道系统在做什么，看下方“当前焦点”和“最近事件”即可。`
    }
    return `${focusTask?.title ?? '当前任务'} 正在推进。通常现在只需要等待结果，除非你要打断或切换任务。`
  }

  if (controlPlane.systemStatus === 'attention') {
    return attentionItem?.summary || '先看“需要关注”，再执行推荐动作。这里通常表示失败、阻塞或需要人工确认。'
  }

  if (controlPlane.systemStatus === 'ready') {
    return preferredAction
      ? `最直接的下一步就是点「${preferredAction.label}」。`
      : '系统已经准备好继续推进，但当前没有明确的推荐动作。'
  }

  if (controlPlane.systemStatus === 'idle' && tasksCount === 0) {
    return '先创建一张真实任务。任务创建后，KAM 才能围绕 refs、snapshot、run 和后续计划工作。'
  }

  if (controlPlane.systemStatus === 'idle') {
    return preferredAction
      ? `当前没有自动进行中的动作。你可以直接点「${preferredAction.label}」，或者打开某张任务手动推进。`
      : '当前没有自动进行中的动作。你可以打开现有任务，或者新建一张任务开始。'
  }

  return controlPlane.systemSummary || '你可以先看推荐动作，再决定是否继续推进。'
}

const firstUseSteps = [
  {
    title: '1. 先看“现在状态”',
    summary: '这里会直接告诉你系统是在执行、空闲，还是需要你介入。',
  },
  {
    title: '2. 想继续推进就点“推荐动作”',
    summary: '不用先理解所有对象，优先执行当前最合适的一步。',
  },
  {
    title: '3. 想自己开始一项新工作',
    summary: '点击“新建任务”，写清楚目标，再补 refs、snapshot 和 run。',
  },
] as const

export function FrontDoorPanel({
  controlPlane,
  tasksCount,
  actionPending,
  onAction,
  onOpenTask,
  onCreateTask,
}: {
  controlPlane: OperatorControlPlaneResponse | null
  tasksCount: number
  actionPending: OperatorActionKey | null
  onAction: (action: OperatorActionRecord) => void
  onOpenTask: (taskId: string) => void
  onCreateTask: () => void
}) {
  const focusTask = controlPlane?.focus.task ?? controlPlane?.focus.scopeTask ?? null
  const activeRun = controlPlane?.focus.activeRun ?? null
  const preferredAction = controlPlane?.actions.find((action) => !action.disabled) ?? null
  const tone = systemStatusTone(controlPlane?.systemStatus ?? null)

  return (
    <section className="feed-card frontdoor-card">
      <div className="frontdoor-layout">
        <div className="frontdoor-hero">
          <div className="feed-card-title-stack">
            <div className="feed-card-title">先看这里</div>
            <div className="feed-card-subtle">你不需要先理解 KAM 的内部模型。先看现在发生了什么，再决定下一步点哪里。</div>
          </div>

          <div className={`frontdoor-status-pill is-${tone}`}>
            现在状态：{systemStatusLabel(controlPlane?.systemStatus ?? null)}
          </div>
          <div className="frontdoor-summary">{summaryHeadline(controlPlane, tasksCount)}</div>
          <div className="frontdoor-copy">{summaryDetail(controlPlane, tasksCount)}</div>

          <div className="task-chip-row">
            <span className="file-chip">任务数 · {tasksCount}</span>
            {focusTask ? <span className="file-chip">当前任务 · {focusTask.title}</span> : null}
            {activeRun ? <span className="file-chip">当前 Run · {activeRun.agent}</span> : null}
            {controlPlane?.globalAutoDrive ? (
              <span className="file-chip">全局无人值守 · {controlPlane.globalAutoDrive.enabled ? '已开启' : '未开启'}</span>
            ) : null}
          </div>

          <div className="frontdoor-actions">
            {preferredAction ? (
              <button
                type="button"
                className={buttonClassForTone(preferredAction.tone)}
                disabled={actionPending !== null}
                onClick={() => onAction(preferredAction)}
              >
                {actionPending === preferredAction.key ? actionBusyLabel(preferredAction.key) : `推荐动作：${preferredAction.label}`}
              </button>
            ) : null}
            {focusTask ? (
              <button type="button" className="button-secondary" onClick={() => onOpenTask(focusTask.id)}>
                打开当前任务
              </button>
            ) : null}
            <button type="button" className="button-secondary" onClick={onCreateTask}>
              新建任务
            </button>
          </div>
        </div>

        <div className="frontdoor-guide">
          {firstUseSteps.map((step) => (
            <article key={step.title} className="frontdoor-guide-card">
              <strong>{step.title}</strong>
              <span>{step.summary}</span>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}
