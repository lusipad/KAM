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
  const issueMonitorRunningCount = controlPlane?.stats.issueMonitorRunningCount ?? 0

  if (!controlPlane) {
    return '正在读取 KAM 当前状态和推荐动作。'
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
  if (controlPlane.systemStatus === 'idle' && tasksCount === 0 && issueMonitorRunningCount > 0) {
    return '当前还没有任务，但 GitHub issue 自动入池已经在值守'
  }
  if (controlPlane.systemStatus === 'idle' && tasksCount === 0) {
    return '先把第一条工程工作放进 KAM'
  }
  if (controlPlane.systemStatus === 'idle') {
    return '现在没有自动推进中的任务，但控制面已经就位'
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
  const issueMonitorRunningCount = controlPlane?.stats.issueMonitorRunningCount ?? 0
  const issueMonitorAttentionCount = controlPlane?.stats.issueMonitorAttentionCount ?? 0

  if (!controlPlane) {
    return '稍等几秒，KAM 会把当前状态、推荐动作和接管入口读出来。'
  }

  if (controlPlane.systemStatus === 'running') {
    if (activeRun) {
      return `${activeRun.agent} 正在执行 run。通常现在不用操作；如果你只是想知道系统在做什么，看下方“当前焦点”和“最近事件”即可。`
    }
    return `${focusTask?.title ?? '当前任务'} 正在推进。通常现在只需要等待结果，除非你要打断或切换任务。`
  }

  if (controlPlane.systemStatus === 'attention') {
    if (issueMonitorAttentionCount > 0 && attentionItem?.kind?.startsWith('issue_monitor_')) {
      return `${attentionItem.summary} 先处理外部任务源，再继续让 KAM 自动接活。`
    }
    return attentionItem?.summary || '先看“需要关注”，再执行推荐动作。这里通常表示失败、阻塞或需要人工确认。'
  }

  if (controlPlane.systemStatus === 'ready') {
    return preferredAction
      ? `最直接的下一步就是点「${preferredAction.label}」。`
      : '系统已经准备好继续推进，但当前没有明确的推荐动作。'
  }

  if (controlPlane.systemStatus === 'idle' && tasksCount === 0 && issueMonitorRunningCount > 0) {
    return '你现在不用先手工建任务。只要 GitHub 上有新的 issue 变化，KAM 就会把它们送进任务池，开始形成持续推进链路。'
  }

  if (controlPlane.systemStatus === 'idle' && tasksCount === 0) {
    return '先创建一张真实任务，或者接入一个 GitHub repo。任务进入任务池之后，KAM 才能围绕 refs、snapshot、run、artifacts 和后续动作持续推进。'
  }

  if (controlPlane.systemStatus === 'idle') {
    return preferredAction
      ? `当前没有自动进行中的动作。你可以直接点「${preferredAction.label}」，把下一条工程工作继续推下去。`
      : '当前没有自动进行中的动作。你可以打开现有任务，或者新建一张任务开始。'
  }

  return controlPlane.systemSummary || '你可以先看推荐动作，再决定是继续推进、人工接管，还是保持等待。'
}

const proofCards = [
  {
    title: 'Task-native',
    summary: 'GitHub issue、PR 评论和手工任务先进入任务池，再开始 snapshot 与 run。',
    evidence: '证据：任务详情默认就有 Refs、Context Snapshot、Runs 和 Compare。',
  },
  {
    title: 'With receipts',
    summary: '每一轮执行都留下 artifacts，不是跑完只剩一段聊天记录。',
    evidence: '证据：stdout、changed files、summary 和 compare 都能直接复核。',
  },
  {
    title: 'Operator-native',
    summary: '系统可以自动继续推进，但你始终保留人工接管权。',
    evidence: '证据：继续、接下一张、采纳、重试、打断都在控制面第一层。',
  },
] as const

const demoFlowSteps = [
  'GitHub issue / PR comment',
  'Task pool',
  'Runs',
  'Artifacts',
  'Follow-up',
  'Continue',
] as const

const firstUseSteps = [
  {
    title: '1. 先看默认演示链路',
    summary: '首页先把这套产品在演什么讲清楚：外部输入入池、执行、留痕，再继续推进。',
  },
  {
    title: '2. 再打开当前任务看证据',
    summary: '看 Refs、Snapshot、Runs、Artifacts 和 Compare，确认这不是一轮性 prompt wrapper。',
  },
  {
    title: '3. 最后决定要不要接管',
    summary: '如果想继续跑，点推荐动作；如果想人工介入，控制面会直接给出入口。',
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
            <div className="feed-card-title">让 AI 不只写代码，而是持续做工程工作</div>
            <div className="feed-card-subtle">
              KAM 是本地优先的 AI 工程控制面。它把 GitHub issue、PR 评论和手工任务接进来，放进统一任务池，持续推进，并且全程可追踪、可打断、可接管。
            </div>
          </div>

          <div className="task-chip-row">
            <span className="file-chip">Local-first</span>
            <span className="file-chip">GitHub-driven</span>
            <span className="file-chip">Task-native</span>
            <span className="file-chip">Operator control included</span>
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
            {typeof controlPlane?.stats.issueMonitorCount === 'number' && controlPlane.stats.issueMonitorCount > 0 ? (
              <span className="file-chip">
                Issue 自动入池 · {controlPlane.stats.issueMonitorRunningCount}/{controlPlane.stats.issueMonitorCount}
              </span>
            ) : null}
          </div>

          <div className="frontdoor-proof-grid">
            {proofCards.map((card) => (
              <article key={card.title} className="frontdoor-proof-card">
                <div className="frontdoor-section-label">{card.title}</div>
                <strong>{card.summary}</strong>
                <span>{card.evidence}</span>
              </article>
            ))}
          </div>

          <article className="frontdoor-story-card">
            <div className="frontdoor-story-head">
              <div className="frontdoor-section-label">默认演示链路</div>
              <strong>现在这套 demo 讲的是：外部 GitHub 输入怎么被 KAM 接住，并继续推进。</strong>
              <span>先看链路，再点进当前任务核对 runs、artifacts 和后续动作，这样差异点才是可见证据，不是口号。</span>
            </div>
            <div className="frontdoor-story-rail">
              {demoFlowSteps.map((step, index) => (
                <div key={step} className="frontdoor-story-node">
                  {index > 0 ? <span className="frontdoor-story-arrow">→</span> : null}
                  <span className="frontdoor-story-step">{step}</span>
                </div>
              ))}
            </div>
          </article>

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
