import { autoDriveActionLabel, autoDriveReasonLabel, autoDriveStatusLabel } from '@/features/tasks/autoDriveLabels'
import { metadataText } from '@/features/tasks/taskMetadata'
import type { IssueMonitorRecord, OperatorActionKey, OperatorActionRecord, OperatorControlPlaneResponse, TaskRecord } from '@/types/harness'

const guideItems = [
  {
    title: '怎么看状态',
    summary: '先看“总状态 / 当前焦点 / 最近事件”，就能知道现在谁在跑、卡在哪。',
  },
  {
    title: '怎么重新触发',
    summary: '优先用“让 KAM 接下一张”或“继续推进当前任务”；如果只是补跑失败执行，再用“重试最近失败 Run”。',
  },
  {
    title: '怎么打断',
    summary: '“打断当前 Run”会立刻取消正在执行的 agent；“停止无人值守”只会停止后续自动推进。',
  },
  {
    title: '怎么重启',
    summary: '重启不会续跑已中断 run；它会把未完成 run 标记为 failed，并恢复全局调度。',
  },
] as const

function timeLabel(value: string | null) {
  if (!value) {
    return null
  }
  const timestamp = new Date(value)
  if (Number.isNaN(timestamp.getTime())) {
    return value
  }
  return timestamp.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function systemStatusLabel(value: string) {
  if (value === 'running') {
    return '执行中'
  }
  if (value === 'attention') {
    return '待介入'
  }
  if (value === 'ready') {
    return '可推进'
  }
  if (value === 'idle') {
    return '空闲'
  }
  if (value === 'waiting_for_run') {
    return '等待 Run'
  }
  if (value === 'paused') {
    return '已暂停'
  }
  return autoDriveStatusLabel(value)
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

function monitorStatusLabel(value: string) {
  if (value === 'enqueued') {
    return '已入池'
  }
  if (value === 'source-error') {
    return '源错误'
  }
  if (value === 'failed') {
    return '失败'
  }
  if (value === 'idle') {
    return '空闲'
  }
  if (value === 'noop') {
    return '无动作'
  }
  return value
}

function actionBusyLabel(action: OperatorActionKey) {
  if (action === 'start_global_autodrive' || action === 'start_task_autodrive') {
    return '启动中…'
  }
  if (action === 'stop_global_autodrive' || action === 'stop_task_autodrive') {
    return '停止中…'
  }
  if (action === 'restart_global_autodrive') {
    return '重启中…'
  }
  if (action === 'dispatch_next') {
    return '接手中…'
  }
  if (action === 'continue_task_family') {
    return '推进中…'
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

function leaseLabel(controlPlane: OperatorControlPlaneResponse | null) {
  const lease = controlPlane?.globalAutoDrive.lease
  if (!lease) {
    return null
  }
  const owner = lease.hostname && lease.pid ? `${lease.hostname}:${lease.pid}` : lease.ownerId
  if (!owner) {
    return null
  }
  return lease.ownedByCurrentProcess ? `${owner} · 当前实例` : owner
}

function pullNumberLabel(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value)
  }
  if (typeof value === 'string' && value.trim() && /^\d+$/.test(value.trim())) {
    return value.trim()
  }
  return null
}

function sourceMappingLabel(task: TaskRecord | null) {
  const metadata = task?.metadata ?? {}
  const sourceKind = metadataText(metadata.sourceKind)
  const sourceRepo = metadataText(metadata.sourceRepo)
  const sourcePullNumber = pullNumberLabel(metadata.sourcePullNumber)
  const sourceIssueNumber = pullNumberLabel(metadata.sourceIssueNumber)
  if (sourceKind === 'github_pr_review_comments' && sourceRepo && sourcePullNumber) {
    return `GitHub PR 评审 · ${sourceRepo}#${sourcePullNumber}`
  }
  if (sourceKind === 'github_issue' && sourceRepo && sourceIssueNumber) {
    return `GitHub Issue · ${sourceRepo}#${sourceIssueNumber}`
  }
  if (sourceRepo && sourceIssueNumber) {
    return `${sourceRepo}#${sourceIssueNumber}`
  }
  if (sourceRepo && sourcePullNumber) {
    return `${sourceRepo}#${sourcePullNumber}`
  }
  if (sourceRepo) {
    return sourceRepo
  }
  if (sourceKind === 'task') {
    return 'KAM 任务池'
  }
  return sourceKind
}

function targetMappingLabel(task: TaskRecord | null) {
  const metadata = task?.metadata ?? {}
  const remoteUrl = metadataText(metadata.executionRemoteUrl)
  const executionRef = metadataText(metadata.executionRef)
  if (remoteUrl && executionRef) {
    const trimmed = remoteUrl.replace(/\.git$/u, '')
    if (trimmed.startsWith('https://github.com/')) {
      return `${trimmed.replace('https://github.com/', '')}:${executionRef}`
    }
    return `${trimmed}:${executionRef}`
  }
  return task?.repoPath ?? null
}

function restartSemanticsLabel(controlPlane: OperatorControlPlaneResponse | null) {
  if (controlPlane?.globalAutoDrive.enabled) {
    return '不会续跑已中断 run；启动恢复时，未完成 run 会标记为 failed；若全局无人值守此前已开启，supervisor 会恢复并继续调度。'
  }
  return '不会续跑已中断 run；启动恢复时，未完成 run 会标记为 failed；需要时可手动重启 supervisor 重新恢复调度。'
}

function issueMonitorBusyLabel(value: string | null) {
  if (value === 'register') {
    return '注册中…'
  }
  if (value?.startsWith('run:')) {
    return '重扫中…'
  }
  if (value?.startsWith('remove:')) {
    return '移除中…'
  }
  return '处理中…'
}

function monitorToneLabel(monitor: IssueMonitorRecord) {
  if (monitor.tone === 'red') {
    return '异常'
  }
  if (monitor.tone === 'amber') {
    return '待处理'
  }
  if (monitor.tone === 'green') {
    return '正常'
  }
  return '观察中'
}

export function OperatorPanel({
  controlPlane,
  actionPending,
  issueMonitorDraft,
  issueMonitorPending,
  refreshing,
  selectedTaskBlockedReason,
  onRefresh,
  onAction,
  onIssueMonitorDraftChange,
  onSaveIssueMonitor,
  onRunIssueMonitor,
  onDeleteIssueMonitor,
  onSelectTask,
}: {
  controlPlane: OperatorControlPlaneResponse | null
  actionPending: OperatorActionKey | null
  issueMonitorDraft: { repo: string; repoPath: string }
  issueMonitorPending: string | null
  refreshing: boolean
  selectedTaskBlockedReason: string | null
  onRefresh: () => void
  onAction: (action: OperatorActionRecord) => void
  onIssueMonitorDraftChange: (value: { repo: string; repoPath: string }) => void
  onSaveIssueMonitor: () => void
  onRunIssueMonitor: (repo: string) => void
  onDeleteIssueMonitor: (repo: string) => void
  onSelectTask: (taskId: string) => void
}) {
  const currentTask = controlPlane?.focus.task ?? null
  const scopeTask = controlPlane?.focus.scopeTask ?? null
  const activeRun = controlPlane?.focus.activeRun ?? null
  const globalAutoDrive = controlPlane?.globalAutoDrive ?? null
  const issueMonitors = controlPlane?.issueMonitors ?? []
  const recentEvents = controlPlane?.recentEvents.slice().reverse().slice(0, 4) ?? []
  const lease = leaseLabel(controlPlane)
  const focusSummary = selectedTaskBlockedReason ?? controlPlane?.focus.summary ?? null
  const mappingTask = currentTask ?? scopeTask
  const sourceMapping = sourceMappingLabel(mappingTask)
  const targetMapping = targetMappingLabel(mappingTask)
  const restartSemantics = restartSemanticsLabel(controlPlane)
  const monitorRegisteredCount = controlPlane?.stats.issueMonitorCount ?? issueMonitors.length
  const monitorRunningCount = controlPlane?.stats.issueMonitorRunningCount ?? issueMonitors.filter((item) => item.running).length
  const monitorAttentionCount = controlPlane?.stats.issueMonitorAttentionCount ?? issueMonitors.filter((item) => item.attention).length

  return (
    <section className="feed-card operator-card">
      <div className="feed-card-head">
        <div className="feed-card-title-stack">
          <div className="feed-card-title">详细状态与人工介入</div>
          <div className="feed-card-subtle">{selectedTaskBlockedReason ?? controlPlane?.systemSummary ?? '这里是更细的系统状态、推荐动作和人工介入入口。'}</div>
        </div>
        <button type="button" className="button-secondary" disabled={refreshing} onClick={onRefresh}>
          {refreshing ? '刷新中…' : '刷新状态'}
        </button>
      </div>

      <div className="task-chip-row">
        <span className="file-chip">总状态 · {controlPlane ? systemStatusLabel(controlPlane.systemStatus) : '读取中'}</span>
        {globalAutoDrive ? <span className="file-chip">全局 · {globalAutoDrive.enabled ? '已开启' : '未开启'}</span> : null}
        {globalAutoDrive?.status ? <span className="file-chip">阶段 · {autoDriveStatusLabel(globalAutoDrive.status)}</span> : null}
        {typeof controlPlane?.stats.runningRunCount === 'number' ? (
          <span className="file-chip">Running · {controlPlane.stats.runningRunCount}</span>
        ) : null}
        {typeof controlPlane?.stats.blockedTaskCount === 'number' ? (
          <span className="file-chip">Blocked · {controlPlane.stats.blockedTaskCount}</span>
        ) : null}
        {typeof controlPlane?.stats.failedTaskCount === 'number' ? (
          <span className="file-chip">Failed · {controlPlane.stats.failedTaskCount}</span>
        ) : null}
        {typeof controlPlane?.stats.passedRunAwaitingAdoptCount === 'number' ? (
          <span className="file-chip">待采纳 · {controlPlane.stats.passedRunAwaitingAdoptCount}</span>
        ) : null}
        {monitorRegisteredCount > 0 ? <span className="file-chip">Issue 监控 · {monitorRegisteredCount}</span> : null}
        {monitorRunningCount > 0 ? <span className="file-chip">Monitor Running · {monitorRunningCount}</span> : null}
        {monitorAttentionCount > 0 ? <span className="file-chip">Monitor 异常 · {monitorAttentionCount}</span> : null}
        {lease ? <span className="file-chip">Lease · {lease}</span> : null}
        {globalAutoDrive?.lease?.stale ? <span className="file-chip">Lease 状态 · stale</span> : null}
        {timeLabel(controlPlane?.generatedAt ?? null) ? <span className="file-chip">刷新时间 · {timeLabel(controlPlane?.generatedAt ?? null)}</span> : null}
      </div>

      {currentTask || scopeTask || activeRun || controlPlane?.focus.summary ? (
        <div className="operator-focus">
          <div className="group-label">当前焦点</div>
          <div className="task-chip-row">
            {currentTask ? (
              <button type="button" className="task-link-button" onClick={() => onSelectTask(currentTask.id)}>
                任务 · {currentTask.title}
              </button>
            ) : null}
            {scopeTask && scopeTask.id !== currentTask?.id ? (
              <button type="button" className="task-link-button" onClick={() => onSelectTask(scopeTask.id)}>
                Scope · {scopeTask.title}
              </button>
            ) : null}
            {activeRun ? <span className="file-chip">Run · {activeRun.id}</span> : null}
            {globalAutoDrive?.currentRunId && globalAutoDrive.currentRunId !== activeRun?.id ? (
              <span className="file-chip">Supervisor Run · {globalAutoDrive.currentRunId}</span>
            ) : null}
            {globalAutoDrive?.lastReason ? <span className="file-chip">最近原因 · {autoDriveReasonLabel(globalAutoDrive.lastReason)}</span> : null}
            {globalAutoDrive?.lastAction ? <span className="file-chip">最近动作 · {autoDriveActionLabel(globalAutoDrive.lastAction)}</span> : null}
          </div>
          {focusSummary ? <div className="feed-card-subtle">{focusSummary}</div> : null}
        </div>
      ) : null}

      {sourceMapping || targetMapping || restartSemantics ? (
        <section className="operator-section">
          <div className="group-label">现实对应</div>
          <div className="task-list">
            <article className="task-list-row">
              <div className="task-list-copy">
                {sourceMapping ? <span>来源：{sourceMapping}</span> : null}
                {targetMapping ? <span>目标：{targetMapping}</span> : null}
                <span>重启语义：{restartSemantics}</span>
              </div>
            </article>
          </div>
        </section>
      ) : null}

      <section className="operator-section">
        <div className="group-label">值守说明</div>
        <div className="task-list">
          {guideItems.map((item) => (
            <article key={item.title} className="task-list-row">
              <div className="task-list-copy">
                <strong>{item.title}</strong>
                <span>{item.summary}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="operator-section">
        <div className="group-label">GitHub Issue 自动入池</div>
        <div className="task-list">
          <article className="task-list-row">
            <div className="task-list-copy">
              <strong>注册一个仓库后，KAM 运行期间会持续轮询；重启后会自动恢复。</strong>
              <span>如果你没有任务，但希望系统自己从 GitHub 接活，优先在这里注册 Issue monitor。</span>
              <div className="task-chip-row">
                <span className="file-chip">已注册 · {monitorRegisteredCount}</span>
                <span className="file-chip">运行中 · {monitorRunningCount}</span>
                {monitorAttentionCount > 0 ? <span className="file-chip">需要处理 · {monitorAttentionCount}</span> : null}
              </div>
            </div>
          </article>
        </div>
        <div className="task-inline-form">
          <input
            className="watcher-input"
            value={issueMonitorDraft.repo}
            onChange={(event) => onIssueMonitorDraftChange({ ...issueMonitorDraft, repo: event.target.value })}
            placeholder="GitHub repo，例如 lusipad/KAM"
          />
          <input
            className="watcher-input"
            value={issueMonitorDraft.repoPath}
            onChange={(event) => onIssueMonitorDraftChange({ ...issueMonitorDraft, repoPath: event.target.value })}
            placeholder="本地 repoPath（可留空）"
          />
          <button type="button" className="button-primary" disabled={Boolean(issueMonitorPending) || !issueMonitorDraft.repo.trim()} onClick={onSaveIssueMonitor}>
            {issueMonitorPending === 'register' ? issueMonitorBusyLabel(issueMonitorPending) : '注册 / 更新 Monitor'}
          </button>
        </div>
        {issueMonitors.length ? (
          <div className="task-list">
            {issueMonitors.map((monitor) => (
              <article key={monitor.repo} className="task-list-row">
                <div className="task-list-copy">
                  <strong>{monitor.repo}</strong>
                  <span>{monitor.summary}</span>
                  <div className="task-chip-row">
                    <span className="file-chip">状态 · {monitorStatusLabel(monitor.status)}</span>
                    <span className="file-chip">运行态 · {monitor.running ? '运行中' : '未运行'}</span>
                    <span className="file-chip">健康度 · {monitorToneLabel(monitor)}</span>
                    {monitor.lastCheckedAt ? <span className="file-chip">上次检查 · {timeLabel(monitor.lastCheckedAt) ?? monitor.lastCheckedAt}</span> : null}
                    {typeof monitor.issueCount === 'number' ? <span className="file-chip">Issue 总数 · {monitor.issueCount}</span> : null}
                    {typeof monitor.changedIssueCount === 'number' ? <span className="file-chip">本轮变化 · {monitor.changedIssueCount}</span> : null}
                    {monitor.repoPath ? <span className="file-chip">repoPath · {monitor.repoPath}</span> : null}
                    {monitor.taskIds[0] ? (
                      <button type="button" className="task-link-button" onClick={() => onSelectTask(monitor.taskIds[0])}>
                        打开最近任务
                      </button>
                    ) : null}
                  </div>
                </div>
                <div className="task-list-actions">
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={Boolean(issueMonitorPending)}
                    onClick={() => onRunIssueMonitor(monitor.repo)}
                  >
                    {issueMonitorPending === `run:${monitor.repo}` ? issueMonitorBusyLabel(issueMonitorPending) : '立即扫一轮'}
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={Boolean(issueMonitorPending)}
                    onClick={() => onDeleteIssueMonitor(monitor.repo)}
                  >
                    {issueMonitorPending === `remove:${monitor.repo}` ? issueMonitorBusyLabel(issueMonitorPending) : '移除'}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-panel">当前还没有注册任何 GitHub Issue 自动入池。注册后，新 issue 会自动进入 KAM 任务池。</div>
        )}
      </section>

      <div className="operator-sections">
        <section className="operator-section">
          <div className="group-label">可执行动作</div>
          <div className="task-list operator-action-list">
            {controlPlane?.actions?.length ? (
              controlPlane.actions.map((action) => {
                const blockedBySelection =
                  Boolean(selectedTaskBlockedReason)
                  && action.taskId === currentTask?.id
                  && (action.key === 'continue_task_family' || action.key === 'start_task_autodrive')
                const disabled = action.disabled || blockedBySelection || actionPending !== null
                const disabledReason = blockedBySelection ? selectedTaskBlockedReason : action.disabledReason
                return (
                  <article key={`${action.key}-${action.taskId ?? 'global'}-${action.runId ?? 'none'}`} className="task-list-row operator-action-row">
                  <div className="task-list-copy">
                    <strong>{action.label}</strong>
                    <span>{action.description}</span>
                    {disabledReason ? <span>当前不可用：{disabledReason}</span> : null}
                  </div>
                  <div className="task-list-actions">
                    <button
                      type="button"
                      className={buttonClassForTone(action.tone)}
                      disabled={disabled}
                      onClick={() => onAction(action)}
                    >
                      {actionPending === action.key ? actionBusyLabel(action.key) : action.label}
                    </button>
                  </div>
                  </article>
                )
              })
            ) : (
              <div className="empty-panel">当前没有可直接执行的 operator 动作。</div>
            )}
          </div>
        </section>

        <section className="operator-section">
          <div className="group-label">需要关注</div>
          <div className="task-list">
            {controlPlane?.attention?.length ? (
              controlPlane.attention.map((item) => (
                <article key={`${item.kind}-${item.taskId ?? 'global'}-${item.runId ?? 'none'}`} className="task-list-row">
                  <div className="task-list-copy">
                    <strong>{item.title}</strong>
                    <span>{item.summary}</span>
                    <div className="task-chip-row">
                      <span className="file-chip">类型 · {item.kind}</span>
                      {item.taskId ? (
                        <button type="button" className="task-link-button" onClick={() => onSelectTask(item.taskId!)}>
                          打开任务
                        </button>
                      ) : null}
                      {item.runId ? <span className="file-chip">Run · {item.runId}</span> : null}
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <div className="empty-panel">当前没有需要人工介入的高优先级事项。</div>
            )}
          </div>
        </section>
      </div>

      {recentEvents.length ? (
        <section className="operator-section">
          <div className="group-label">最近事件</div>
          <div className="task-list">
            {recentEvents.map((event) => (
              <article key={`${event.recordedAt}-${event.reason ?? event.status ?? 'event'}`} className="task-list-row">
                <div className="task-list-copy">
                  <strong>{event.summary || autoDriveStatusLabel(event.status)}</strong>
                  <span>{timeLabel(event.recordedAt) || '刚刚'}</span>
                  <div className="task-chip-row">
                    {event.status ? <span className="file-chip">阶段 · {autoDriveStatusLabel(event.status)}</span> : null}
                    {event.action ? <span className="file-chip">动作 · {autoDriveActionLabel(event.action)}</span> : null}
                    {event.reason ? <span className="file-chip">原因 · {autoDriveReasonLabel(event.reason)}</span> : null}
                    {event.taskId ? (
                      <button type="button" className="task-link-button" onClick={() => onSelectTask(event.taskId!)}>
                        任务 · {event.taskId}
                      </button>
                    ) : null}
                    {event.runId ? <span className="file-chip">Run · {event.runId}</span> : null}
                  </div>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  )
}
