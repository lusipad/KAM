import { useMemo } from 'react'

import { PromptComposer } from '@/components/PromptComposer'
import { formatRelativeTime } from '@/lib/ui'
import { autoDriveActionLabel, autoDriveReasonLabel, autoDriveStatusLabel } from '@/features/tasks/autoDriveLabels'
import { TaskRunCard } from '@/features/tasks/TaskRunCard'
import type {
  AutoDriveEventRecord,
  RunRecord,
  SuggestedTaskRefRecord,
  TaskContinueResponse,
  TaskDependencyRecord,
  TaskDetail,
  TaskPlanSuggestion,
  TaskRecord,
} from '@/types/harness'

type TaskWorkbenchProps = {
  task: TaskDetail | null
  taskDraft: {
    title: string
    description: string
    repoPath: string
    status: string
    priority: string
    labelsText: string
  }
  loading: boolean
  runPrompt: string
  runAgent: 'codex' | 'claude-code'
  refDraft: { kind: string; label: string; value: string }
  dependencyDraft: string
  snapshotFocus: string
  selectedRunId: string | null
  creatingRun: boolean
  addingRef: boolean
  addingDependency: boolean
  creatingSnapshot: boolean
  creatingCompare: boolean
  creatingPlan: boolean
  continueDecision: TaskContinueResponse | null
  savingTask: boolean
  taskBlocked: boolean
  plannedTasks: TaskRecord[]
  planSuggestions: TaskPlanSuggestion[]
  onRunPromptChange: (value: string) => void
  onRunAgentChange: (agent: 'codex' | 'claude-code') => void
  onTaskDraftChange: (draft: {
    title: string
    description: string
    repoPath: string
    status: string
    priority: string
    labelsText: string
  }) => void
  onSaveTask: () => void
  onCreatePlan: () => void
  onRunRecommendedTask: () => void
  onCreateRun: () => void
  onRefDraftChange: (draft: { kind: string; label: string; value: string }) => void
  onAddRef: () => void
  onDeleteRef: (refId: string) => void
  onDependencyDraftChange: (value: string) => void
  onAddDependency: () => void
  onDeleteDependency: (dependsOnTaskId: string) => void
  onSnapshotFocusChange: (value: string) => void
  onCreateSnapshot: () => void
  onCreateCompare: () => void
  onSelectRun: (runId: string) => void
  onOpenPlannedTask: (task: TaskRecord) => void
  onRunPlannedTask: (task: TaskRecord) => void
  onAdoptRun: (runId: string) => void
  onRetryRun: (runId: string) => void
}

function latestRunLabel(run: RunRecord | null) {
  if (!run) {
    return '还没有 run'
  }
  return `${run.agent} · ${run.status} · ${formatRelativeTime(run.createdAt)}`
}

function metadataText(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function metadataBoolean(value: unknown) {
  return value === true
}

function metadataList(value: unknown) {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function metadataSuggestedRefs(value: unknown): SuggestedTaskRefRecord[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') {
      return []
    }
    const candidate = item as Record<string, unknown>
    const kind = typeof candidate.kind === 'string' ? candidate.kind.trim() : ''
    const label = typeof candidate.label === 'string' ? candidate.label.trim() : ''
    const refValue = typeof candidate.value === 'string' ? candidate.value.trim() : ''
    if (!kind || !label || !refValue) {
      return []
    }
    return [
      {
        kind,
        label,
        value: refValue,
        metadata: candidate.metadata && typeof candidate.metadata === 'object' ? (candidate.metadata as Record<string, unknown>) : {},
      },
    ]
  })
}

function metadataAutoDriveEvents(value: unknown): AutoDriveEventRecord[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') {
      return []
    }
    const candidate = item as Record<string, unknown>
    const recordedAt = typeof candidate.recordedAt === 'string' ? candidate.recordedAt.trim() : ''
    if (!recordedAt) {
      return []
    }
    const text = (entry: string) => {
      const raw = candidate[entry]
      return typeof raw === 'string' && raw.trim() ? raw.trim() : null
    }
    return [
      {
        recordedAt,
        status: text('status'),
        action: text('action'),
        reason: text('reason'),
        summary: text('summary'),
        error: text('error'),
        taskId: text('taskId'),
        scopeTaskId: text('scopeTaskId'),
        runId: text('runId'),
        runTaskId: text('runTaskId'),
      },
    ]
  })
}

function planningReasonLabel(reason: string | null) {
  if (reason === 'failed_run_follow_up') {
    return '失败修复'
  }
  if (reason === 'passed_run_not_adopted') {
    return '采纳收口'
  }
  if (reason === 'review_compare_follow_up') {
    return 'compare 推进'
  }
  if (reason === 'task_next_step') {
    return '下一步'
  }
  return null
}

function firstLine(value: string) {
  return value.split('\n').find((line) => line.trim()) ?? value
}

function plannerAgentLabel(value: string | null) {
  if (value === 'codex') {
    return 'Codex'
  }
  if (value === 'claude-code') {
    return 'Claude Code'
  }
  return null
}

function dependencyStatusLabel(dependency: TaskDependencyRecord) {
  if (dependency.missing) {
    return '缺失'
  }
  if (dependency.resolved) {
    return '已满足'
  }
  if (dependency.status === 'verified' || dependency.status === 'done') {
    return '已满足'
  }
  if (dependency.status === 'failed') {
    return '失败待修'
  }
  if (dependency.status === 'blocked') {
    return '被阻塞'
  }
  if (dependency.status === 'in_progress') {
    return '进行中'
  }
  if (dependency.status === 'open') {
    return '待完成'
  }
  return dependency.status
}

export function TaskWorkbench({
  task,
  taskDraft,
  loading,
  runPrompt,
  runAgent,
  refDraft,
  dependencyDraft,
  snapshotFocus,
  selectedRunId,
  creatingRun,
  addingRef,
  addingDependency,
  creatingSnapshot,
  creatingCompare,
  creatingPlan,
  continueDecision,
  savingTask,
  taskBlocked,
  plannedTasks,
  planSuggestions,
  onRunPromptChange,
  onRunAgentChange,
  onTaskDraftChange,
  onSaveTask,
  onCreatePlan,
  onRunRecommendedTask,
  onCreateRun,
  onRefDraftChange,
  onAddRef,
  onDeleteRef,
  onDependencyDraftChange,
  onAddDependency,
  onDeleteDependency,
  onSnapshotFocusChange,
  onCreateSnapshot,
  onCreateCompare,
  onSelectRun,
  onOpenPlannedTask,
  onRunPlannedTask,
  onAdoptRun,
  onRetryRun,
}: TaskWorkbenchProps) {
  const selectedRun = useMemo(
    () => task?.runs.find((run) => run.id === selectedRunId) ?? task?.runs.at(-1) ?? null,
    [selectedRunId, task],
  )
  const parentTaskId = metadataText(task?.metadata.parentTaskId)
  const currentPlanningReason = planningReasonLabel(metadataText(task?.metadata.planningReason))
  const recommendedPrompt = metadataText(task?.metadata.recommendedPrompt)
  const recommendedAgent = plannerAgentLabel(metadataText(task?.metadata.recommendedAgent))
  const acceptanceChecks = metadataList(task?.metadata.acceptanceChecks)
  const suggestedRefs = metadataSuggestedRefs(task?.metadata.suggestedRefs)
  const autoDriveEnabled = metadataBoolean(task?.metadata.autoDriveEnabled)
  const autoDriveStatus = metadataText(task?.metadata.autoDriveStatus)
  const autoDriveLastAction = autoDriveActionLabel(metadataText(task?.metadata.autoDriveLastAction))
  const autoDriveLastReason = autoDriveReasonLabel(metadataText(task?.metadata.autoDriveLastReason))
  const autoDriveLastSummary = metadataText(task?.metadata.autoDriveLastSummary)
  const autoDriveRecentEvents = metadataAutoDriveEvents(task?.metadata.autoDriveRecentEvents)
  const dependencyState = task?.dependencyState
  const dependencySummary = dependencyState?.summary ?? null

  if (loading) {
    return <div className="empty-panel">正在加载任务…</div>
  }

  if (!task) {
    return (
      <div className="empty-state">
        <div className="empty-icon">T</div>
        <div className="empty-title">Task-First Harness</div>
        <div className="empty-copy">先从左侧创建一个任务，再挂 refs、生成 snapshot、启动 runs。</div>
      </div>
    )
  }

  return (
    <div className="task-workbench">
      <div className="task-scroll">
        <div className="thread-column">
          <section className="feed-card task-hero-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">{task.title}</div>
                <div className="feed-card-subtle">
                  {task.description || '当前任务还没有补充描述。'}
                </div>
              </div>
              <span className="feed-card-badge">{task.priority}</span>
            </div>
            <div className="task-chip-row">
              <span className="file-chip">状态 · {task.status}</span>
              {task.repoPath ? <span className="file-chip">Repo · {task.repoPath}</span> : null}
              {dependencyState ? (
                <span className="file-chip">依赖 · {dependencyState.ready ? '已满足' : '阻塞中'}</span>
              ) : null}
              {task.labels.map((label) => (
                <span key={label} className="file-chip">
                  {label}
                </span>
              ))}
            </div>
            {dependencySummary ? (
              <div className="task-list">
                <article className="task-list-row">
                  <div className="task-list-copy">
                    <strong>依赖状态</strong>
                    <span>{dependencySummary}</span>
                    {dependencyState?.blockedBy.length ? (
                      <div className="task-chip-row">
                        {dependencyState.blockedBy.map((dependency) => (
                          <span key={dependency.taskId} className="file-chip">
                            {dependency.title} · {dependencyStatusLabel(dependency)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </article>
              </div>
            ) : null}
            {autoDriveStatus || autoDriveLastSummary ? (
              <div className="task-list">
                <article className="task-list-row">
                  <div className="task-list-copy">
                    <strong>无人值守</strong>
                    <span>{autoDriveLastSummary || '当前任务族已经进入自动托管。'}</span>
                    <div className="task-chip-row">
                      <span className="file-chip">状态 · {autoDriveEnabled ? '已开启' : '未开启'}</span>
                      {autoDriveStatus ? <span className="file-chip">阶段 · {autoDriveStatusLabel(autoDriveStatus)}</span> : null}
                      {autoDriveLastAction ? <span className="file-chip">动作 · {autoDriveLastAction}</span> : null}
                      {autoDriveLastReason ? <span className="file-chip">原因 · {autoDriveLastReason}</span> : null}
                    </div>
                  </div>
                </article>
                {autoDriveRecentEvents.slice().reverse().slice(0, 4).map((event) => (
                  <article key={`${event.recordedAt}-${event.reason ?? event.status ?? 'event'}`} className="task-list-row">
                    <div className="task-list-copy">
                      <strong>{event.summary || autoDriveStatusLabel(event.status)}</strong>
                      <span>{formatRelativeTime(event.recordedAt)}</span>
                      <div className="task-chip-row">
                        {event.status ? <span className="file-chip">阶段 · {autoDriveStatusLabel(event.status)}</span> : null}
                        {event.action ? <span className="file-chip">动作 · {autoDriveActionLabel(event.action)}</span> : null}
                        {event.reason ? <span className="file-chip">原因 · {autoDriveReasonLabel(event.reason)}</span> : null}
                        {event.runId ? <span className="file-chip">Run · {event.runId}</span> : null}
                        {event.runTaskId ? <span className="file-chip">任务 · {event.runTaskId}</span> : null}
                        {event.error ? <span className="file-chip">错误 · {event.error}</span> : null}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : null}
            <div className="task-inline-form">
              <input
                className="watcher-input"
                value={taskDraft.title}
                onChange={(event) => onTaskDraftChange({ ...taskDraft, title: event.target.value })}
                placeholder="任务标题"
              />
              <input
                className="watcher-input"
                value={taskDraft.status}
                onChange={(event) => onTaskDraftChange({ ...taskDraft, status: event.target.value })}
                placeholder="状态"
              />
              <input
                className="watcher-input"
                value={taskDraft.priority}
                onChange={(event) => onTaskDraftChange({ ...taskDraft, priority: event.target.value })}
                placeholder="优先级"
              />
              <button type="button" className="button-primary" disabled={savingTask || !taskDraft.title.trim()} onClick={onSaveTask}>
                保存任务设置
              </button>
            </div>
            <div className="task-inline-form">
              <input
                className="watcher-input"
                value={taskDraft.repoPath}
                onChange={(event) => onTaskDraftChange({ ...taskDraft, repoPath: event.target.value })}
                placeholder="仓库路径"
              />
              <input
                className="watcher-input"
                value={taskDraft.labelsText}
                onChange={(event) => onTaskDraftChange({ ...taskDraft, labelsText: event.target.value })}
                placeholder="标签，逗号分隔"
              />
            </div>
            <input
              className="watcher-input"
              value={taskDraft.description}
              onChange={(event) => onTaskDraftChange({ ...taskDraft, description: event.target.value })}
              placeholder="任务描述"
            />
            <div className="task-list">
              <article className="task-list-row">
                <div className="task-list-copy">
                  <strong>任务依赖</strong>
                  <span>{dependencySummary || '当前没有显式依赖。'}</span>
                  {dependencyState?.dependencies.length ? (
                    <div className="task-chip-row">
                      {dependencyState.dependencies.map((dependency) => (
                        <span key={dependency.taskId} className="file-chip">
                          {dependency.title} · {dependencyStatusLabel(dependency)}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </article>
            </div>
            <div className="task-inline-form">
              <input
                className="watcher-input"
                value={dependencyDraft}
                onChange={(event) => onDependencyDraftChange(event.target.value)}
                placeholder="依赖任务 ID"
              />
              <button type="button" className="button-primary" disabled={addingDependency || !dependencyDraft.trim()} onClick={onAddDependency}>
                添加依赖
              </button>
            </div>
            {dependencyState?.dependencies.length ? (
              <div className="task-list">
                {dependencyState.dependencies.map((dependency) => (
                  <article key={dependency.taskId} className="task-list-row">
                    <div className="task-list-copy">
                      <strong>{dependency.title}</strong>
                      <span>
                        {dependency.taskId} · {dependencyStatusLabel(dependency)}
                      </span>
                    </div>
                    <button type="button" className="button-secondary" onClick={() => onDeleteDependency(dependency.taskId)}>
                      移除依赖
                    </button>
                  </article>
                ))}
              </div>
            ) : null}
            {recommendedPrompt || acceptanceChecks.length || suggestedRefs.length ? (
              <div className="task-list">
                <article className="task-list-row">
                  <div className="task-list-copy">
                    <strong>下一轮执行建议</strong>
                    {recommendedAgent ? <span>推荐 Agent · {recommendedAgent}</span> : null}
                    {recommendedPrompt ? <pre className="task-plan-prompt">{recommendedPrompt}</pre> : null}
                    {acceptanceChecks.length ? (
                      <div className="task-guidance-list">
                        {acceptanceChecks.map((item) => (
                          <span key={item}>验收 · {item}</span>
                        ))}
                      </div>
                    ) : null}
                    {suggestedRefs.length ? (
                      <div className="task-chip-row">
                        {suggestedRefs.slice(0, 4).map((ref) => (
                          <span key={`${ref.kind}-${ref.value}`} className="file-chip">
                            {ref.label}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  {recommendedPrompt ? (
                    <div className="task-list-actions">
                      <button type="button" className="button-primary" disabled={creatingRun || taskBlocked} onClick={onRunRecommendedTask}>
                        用推荐 Prompt 开跑
                      </button>
                    </div>
                  ) : null}
                </article>
              </div>
            ) : null}
          </section>

          {continueDecision && (continueDecision.task?.id === task.id || continueDecision.scopeTaskId === task.id) ? (
            <section className="feed-card">
              <div className="feed-card-head">
                <div className="feed-card-title-stack">
                  <div className="feed-card-title">自动推进结果</div>
                  <div className="feed-card-subtle">{continueDecision.summary}</div>
                </div>
                <span className="feed-card-badge">{autoDriveActionLabel(continueDecision.action)}</span>
              </div>
              <div className="task-chip-row">
                {autoDriveReasonLabel(continueDecision.reason) ? (
                  <span className="file-chip">原因 · {autoDriveReasonLabel(continueDecision.reason)}</span>
                ) : null}
                {continueDecision.source ? <span className="file-chip">来源 · {continueDecision.source}</span> : null}
                {continueDecision.plannedFromTaskId ? <span className="file-chip">父任务 · {continueDecision.plannedFromTaskId}</span> : null}
                {continueDecision.run?.id ? <span className="file-chip">Run · {continueDecision.run.id}</span> : null}
              </div>
            </section>
          ) : null}

          <section className="feed-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">让 KAM 自己排工作</div>
                <div className="feed-card-subtle">
                  {taskBlocked ? dependencySummary || '当前任务仍被依赖阻塞。' : '基于当前任务的 run、compare 和上下文，直接拆出下一轮 follow-up tasks。'}
                </div>
              </div>
              <button type="button" className="button-primary" disabled={creatingPlan || taskBlocked} onClick={onCreatePlan}>
                {creatingPlan ? '正在拆任务…' : '让 KAM 自己排工作'}
              </button>
            </div>

            {parentTaskId || currentPlanningReason ? (
              <div className="task-chip-row">
                {currentPlanningReason ? <span className="file-chip">来源 · {currentPlanningReason}</span> : null}
                {parentTaskId ? <span className="file-chip">父任务 · {parentTaskId}</span> : null}
              </div>
            ) : null}

            {plannedTasks.length ? (
              <div className="task-list">
                {plannedTasks.map((plannedTask, index) => {
                  const suggestion = planSuggestions[index] ?? null
                  const plannedReason = planningReasonLabel(metadataText(plannedTask.metadata.planningReason))
                  const sourceRunId = metadataText(plannedTask.metadata.sourceRunId)
                  const sourceCompareId = metadataText(plannedTask.metadata.sourceCompareId)
                  const plannedPrompt = metadataText(plannedTask.metadata.recommendedPrompt) ?? suggestion?.recommendedPrompt ?? null
                  const plannedAgent = plannerAgentLabel(metadataText(plannedTask.metadata.recommendedAgent) ?? suggestion?.recommendedAgent ?? null)
                  const plannedChecks = metadataList(plannedTask.metadata.acceptanceChecks)
                  const plannedRefs = metadataSuggestedRefs(plannedTask.metadata.suggestedRefs)
                  return (
                    <article key={plannedTask.id} className="task-list-row">
                      <div className="task-list-copy">
                        <strong>{plannedTask.title}</strong>
                        <span>{firstLine(plannedTask.description || suggestion?.description || '已写入左侧任务列表。')}</span>
                        <div className="task-chip-row">
                          <span className="file-chip">优先级 · {plannedTask.priority}</span>
                          {plannedReason ? <span className="file-chip">原因 · {plannedReason}</span> : null}
                          {sourceRunId ? <span className="file-chip">Run · {sourceRunId}</span> : null}
                          {sourceCompareId ? <span className="file-chip">Compare · {sourceCompareId}</span> : null}
                          {plannedAgent ? <span className="file-chip">Agent · {plannedAgent}</span> : null}
                        </div>
                        {plannedPrompt ? <pre className="task-plan-prompt">{firstLine(plannedPrompt)}</pre> : null}
                        {plannedChecks.length ? (
                          <div className="task-guidance-list">
                            {plannedChecks.slice(0, 2).map((item) => (
                              <span key={item}>验收 · {item}</span>
                            ))}
                          </div>
                        ) : null}
                        {plannedRefs.length ? (
                          <div className="task-chip-row">
                            {plannedRefs.slice(0, 3).map((ref) => (
                              <span key={`${ref.kind}-${ref.value}`} className="file-chip">
                                {ref.label}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        {suggestion?.rationale ? <span>{suggestion.rationale}</span> : null}
                      </div>
                      <div className="task-list-actions">
                        <button type="button" className="button-secondary" onClick={() => onOpenPlannedTask(plannedTask)}>
                          打开任务
                        </button>
                        {plannedPrompt ? (
                          <button type="button" className="button-primary" disabled={creatingRun || taskBlocked} onClick={() => onRunPlannedTask(plannedTask)}>
                            直接开跑
                          </button>
                        ) : null}
                      </div>
                    </article>
                  )
                })}
              </div>
            ) : planSuggestions.length ? (
              <div className="task-list">
                {planSuggestions.map((suggestion) => {
                  const plannedReason = planningReasonLabel(metadataText(suggestion.metadata.planningReason))
                  const plannedAgent = plannerAgentLabel(suggestion.recommendedAgent)
                  return (
                    <article key={`${suggestion.title}-${suggestion.rationale}`} className="task-list-row">
                      <div className="task-list-copy">
                        <strong>{suggestion.title}</strong>
                        <span>{firstLine(suggestion.description)}</span>
                        <div className="task-chip-row">
                          <span className="file-chip">优先级 · {suggestion.priority}</span>
                          {plannedReason ? <span className="file-chip">原因 · {plannedReason}</span> : null}
                          {plannedAgent ? <span className="file-chip">Agent · {plannedAgent}</span> : null}
                        </div>
                        {suggestion.recommendedPrompt ? <pre className="task-plan-prompt">{firstLine(suggestion.recommendedPrompt)}</pre> : null}
                        {suggestion.acceptanceChecks.length ? (
                          <div className="task-guidance-list">
                            {suggestion.acceptanceChecks.slice(0, 2).map((item) => (
                              <span key={item}>验收 · {item}</span>
                            ))}
                          </div>
                        ) : null}
                        {suggestion.suggestedRefs.length ? (
                          <div className="task-chip-row">
                            {suggestion.suggestedRefs.slice(0, 3).map((ref) => (
                              <span key={`${ref.kind}-${ref.value}`} className="file-chip">
                                {ref.label}
                              </span>
                            ))}
                          </div>
                        ) : null}
                        <span>{suggestion.rationale}</span>
                      </div>
                    </article>
                  )
                })}
              </div>
            ) : (
              <div className="feed-empty">点击后会把后续任务立即写进左侧任务列表，并支持直接切到新任务继续做。</div>
            )}
          </section>

          <section className="feed-card">
            <div className="feed-card-title">Refs</div>
            <div className="task-inline-form">
              <input
                className="watcher-input"
                value={refDraft.kind}
                onChange={(event) => onRefDraftChange({ ...refDraft, kind: event.target.value })}
                placeholder="kind"
              />
              <input
                className="watcher-input"
                value={refDraft.label}
                onChange={(event) => onRefDraftChange({ ...refDraft, label: event.target.value })}
                placeholder="label"
              />
              <input
                className="watcher-input"
                value={refDraft.value}
                onChange={(event) => onRefDraftChange({ ...refDraft, value: event.target.value })}
                placeholder="value"
              />
              <button type="button" className="button-primary" disabled={addingRef} onClick={onAddRef}>
                添加引用
              </button>
            </div>
            <div className="task-list">
              {task.refs.length ? (
                task.refs.map((ref) => (
                  <article key={ref.id} className="task-list-row">
                    <div className="task-list-copy">
                      <strong>
                        [{ref.kind}] {ref.label}
                      </strong>
                      <span>{ref.value}</span>
                    </div>
                    <button type="button" className="button-secondary" onClick={() => onDeleteRef(ref.id)}>
                      删除
                    </button>
                  </article>
                ))
              ) : (
                <div className="feed-empty">还没有 refs。</div>
              )}
            </div>
          </section>

          <section className="feed-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">Context Snapshot</div>
                <div className="feed-card-subtle">把当前任务和 refs 收敛成可执行上下文。</div>
              </div>
              <button type="button" className="button-primary" disabled={creatingSnapshot} onClick={onCreateSnapshot}>
                生成快照
              </button>
            </div>
            <input
              className="watcher-input"
              value={snapshotFocus}
              onChange={(event) => onSnapshotFocusChange(event.target.value)}
              placeholder="可选 focus，例如：先切前端主入口"
            />
            <div className="task-list">
              {task.snapshots.length ? (
                task.snapshots
                  .slice()
                  .reverse()
                  .map((snapshot) => (
                    <article key={snapshot.id} className="task-list-row">
                      <div className="task-list-copy">
                        <strong>{snapshot.summary}</strong>
                        <span>{snapshot.focus || formatRelativeTime(snapshot.createdAt)}</span>
                      </div>
                    </article>
                  ))
              ) : (
                <div className="feed-empty">还没有 snapshot。</div>
              )}
            </div>
          </section>

          <section className="feed-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">Runs</div>
                <div className="feed-card-subtle">{latestRunLabel(selectedRun)}</div>
              </div>
              <button
                type="button"
                className="button-secondary"
                disabled={task.runs.length < 2 || creatingCompare}
                onClick={onCreateCompare}
              >
                对比最近两个 Run
              </button>
            </div>

            <div className="task-agent-row">
              <button
                type="button"
                className={`watcher-level-button ${runAgent === 'codex' ? 'is-active' : ''}`}
                onClick={() => onRunAgentChange('codex')}
              >
                Codex
              </button>
              <button
                type="button"
                className={`watcher-level-button ${runAgent === 'claude-code' ? 'is-active' : ''}`}
                onClick={() => onRunAgentChange('claude-code')}
              >
                Claude Code
              </button>
            </div>

            <PromptComposer
              value={runPrompt}
              placeholder="输入这轮要执行的任务..."
              isSending={creatingRun}
              disabled={taskBlocked}
              toneLabel={runAgent === 'codex' ? 'Codex' : 'Claude Code'}
              detailLabel={taskBlocked ? dependencySummary || '当前任务仍被依赖阻塞。' : '当前会把任务发给选中的 agent'}
              onChange={onRunPromptChange}
              onSubmit={onCreateRun}
            />

            <div className="task-run-stack">
              {task.runs.length ? (
                task.runs
                  .slice()
                  .reverse()
                  .map((run) => (
                    <div key={run.id} className={`task-run-item ${run.id === selectedRun?.id ? 'is-selected' : ''}`}>
                      <button type="button" className="task-run-select" onClick={() => onSelectRun(run.id)}>
                        选中产物
                      </button>
                      <TaskRunCard run={run} onAdopt={onAdoptRun} onRetry={onRetryRun} disableRetry={taskBlocked} />
                    </div>
                  ))
              ) : (
                <div className="feed-empty">还没有 runs。</div>
              )}
            </div>
          </section>

          <section className="feed-card">
            <div className="feed-card-title">Compare</div>
            <div className="task-list">
              {task.reviews.length ? (
                task.reviews
                  .slice()
                  .reverse()
                  .map((review) => (
                    <article key={review.id} className="task-list-row">
                      <div className="task-list-copy">
                        <strong>{review.title}</strong>
                        <span>{review.summary || '暂无摘要'}</span>
                      </div>
                    </article>
                  ))
              ) : (
                <div className="feed-empty">还没有 compare。</div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
