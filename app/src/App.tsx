import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  addTaskRef,
  adoptRun,
  archiveTask,
  continueTask,
  createTask,
  createTaskCompare,
  createTaskRun,
  deleteTaskRef,
  dispatchNextTask,
  getErrorMessage,
  getGlobalAutoDriveStatus,
  getRunArtifacts,
  getTask,
  listTasks,
  planTaskFollowUps,
  resolveTaskContext,
  startGlobalAutoDrive,
  startTaskAutoDrive,
  stopGlobalAutoDrive,
  stopTaskAutoDrive,
  retryRun,
  updateTask,
} from '@/api/client'
import { TaskPanel } from '@/features/tasks/TaskPanel'
import { TaskSidebar } from '@/features/tasks/TaskSidebar'
import { TaskWorkbench } from '@/features/tasks/TaskWorkbench'
import { AppShell } from '@/layout/AppShell'
import type { ToastItem } from '@/layout/Toast'
import type {
  GlobalAutoDriveResponse,
  RunArtifactRecord,
  SuggestedTaskRefRecord,
  TaskContinueResponse,
  TaskDetail,
  TaskPlanSuggestion,
  TaskRecord,
} from '@/types/harness'

function inferTaskPayload(prompt: string) {
  const compact = prompt.trim().replace(/\s+/g, ' ')
  const repoPath = compact.includes(':\\') || compact.startsWith('/') ? compact : null
  return {
    title: compact.slice(0, 60) || '新任务',
    description: compact || null,
    repoPath,
    labels: ['dogfood'],
  }
}

type TaskDraft = {
  title: string
  description: string
  repoPath: string
  status: string
  priority: string
  labelsText: string
}

function toTaskDraft(task: TaskRecord | TaskDetail | null): TaskDraft {
  if (!task) {
    return {
      title: '',
      description: '',
      repoPath: '',
      status: 'open',
      priority: 'medium',
      labelsText: '',
    }
  }
  return {
    title: task.title,
    description: task.description ?? '',
    repoPath: task.repoPath ?? '',
    status: task.status,
    priority: task.priority,
    labelsText: task.labels.join(', '),
  }
}

function parseLabelsText(value: string) {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}

function parsePlannerPrompt(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function parsePlannerAgent(value: unknown): 'codex' | 'claude-code' {
  return value === 'claude-code' ? 'claude-code' : 'codex'
}

function parsePlannerAcceptanceChecks(value: unknown) {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function parsePlannerSuggestedRefs(value: unknown): SuggestedTaskRefRecord[] {
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

function parseAutoDriveEnabled(value: unknown) {
  return value === true
}

function parseAutoDriveStatus(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function autoDriveStatusLabel(value: string | null) {
  if (value === 'running') {
    return '执行中'
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

function autoDriveReasonLabel(value: string | null) {
  if (value === 'no_high_value_action') {
    return '当前没有更高价值的下一步'
  }
  if (value === 'scope_has_active_run') {
    return '当前仍有 run 在执行'
  }
  if (value === 'global_auto_drive_stopped') {
    return '已手动停止全局无人值守'
  }
  if (value === 'global_auto_drive_step_limit_reached') {
    return '达到单轮步数上限'
  }
  return value
}

function shouldPollTask(detail: TaskDetail | null) {
  if (!detail) {
    return false
  }
  if (detail.runs.some((run) => run.status === 'pending' || run.status === 'running')) {
    return true
  }
  if (!parseAutoDriveEnabled(detail.metadata.autoDriveEnabled)) {
    return false
  }
  const status = parseAutoDriveStatus(detail.metadata.autoDriveStatus)
  return status === 'running' || status === 'waiting_for_run'
}

function shouldPollGlobalAutoDrive(status: GlobalAutoDriveResponse | null) {
  return Boolean(status && (status.enabled || status.running))
}

function readPlanningMetadata(metadata: Record<string, unknown> | null | undefined) {
  const value = metadata ?? {}
  return {
    recommendedPrompt: parsePlannerPrompt(value.recommendedPrompt),
    recommendedAgent: parsePlannerAgent(value.recommendedAgent),
    acceptanceChecks: parsePlannerAcceptanceChecks(value.acceptanceChecks),
    suggestedRefs: parsePlannerSuggestedRefs(value.suggestedRefs),
  }
}

function EmptyTaskState({
  value,
  onChange,
  onSubmit,
  isBusy,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  isBusy: boolean
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">T</div>
      <div className="empty-title">Task-First Harness</div>
      <div className="empty-copy">描述一个真实要推进的任务。KAM 会围绕 task、refs、snapshot、runs 和 artifacts 工作。</div>
      <div className="empty-composer">
        <textarea
          className="task-empty-textarea"
          placeholder="例如：把当前默认前端主入口切成 task-first workbench"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <button type="button" className="button-primary task-empty-button" disabled={isBusy || !value.trim()} onClick={onSubmit}>
          创建任务
        </button>
      </div>
    </div>
  )
}

function App() {
  const [tasks, setTasks] = useState<TaskRecord[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [taskDraft, setTaskDraft] = useState<TaskDraft>(toTaskDraft(null))
  const [loading, setLoading] = useState(false)
  const [panelOpen, setPanelOpen] = useState(true)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [artifacts, setArtifacts] = useState<RunArtifactRecord[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [taskPrompt, setTaskPrompt] = useState('')
  const [runPrompt, setRunPrompt] = useState('')
  const [runAgent, setRunAgent] = useState<'codex' | 'claude-code'>('codex')
  const [creatingTask, setCreatingTask] = useState(false)
  const [creatingRun, setCreatingRun] = useState(false)
  const [addingRef, setAddingRef] = useState(false)
  const [creatingSnapshot, setCreatingSnapshot] = useState(false)
  const [creatingCompare, setCreatingCompare] = useState(false)
  const [creatingPlan, setCreatingPlan] = useState(false)
  const [dispatchingNext, setDispatchingNext] = useState(false)
  const [continuingTask, setContinuingTask] = useState(false)
  const [managingAutoDrive, setManagingAutoDrive] = useState(false)
  const [managingGlobalAutoDrive, setManagingGlobalAutoDrive] = useState(false)
  const [savingTask, setSavingTask] = useState(false)
  const [snapshotFocus, setSnapshotFocus] = useState('')
  const [refDraft, setRefDraft] = useState({ kind: 'file', label: '', value: '' })
  const [plannedTasks, setPlannedTasks] = useState<TaskRecord[]>([])
  const [planSuggestions, setPlanSuggestions] = useState<TaskPlanSuggestion[]>([])
  const [continueDecision, setContinueDecision] = useState<TaskContinueResponse | null>(null)
  const [globalAutoDrive, setGlobalAutoDrive] = useState<GlobalAutoDriveResponse | null>(null)
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const pushToast = useCallback((toast: ToastItem) => {
    setToasts((current) => [...current, toast])
    window.setTimeout(() => {
      setToasts((current) => current.filter((item) => item.id !== toast.id))
    }, 10000)
  }, [])

  const onError = useCallback((error: unknown, fallback: string) => {
    pushToast({
      id: `error-${Date.now()}`,
      message: getErrorMessage(error, fallback),
      tone: 'red',
    })
  }, [pushToast])

  const refreshTasks = useCallback(async (options?: { includeArchived?: boolean }) => {
    const data = await listTasks({ includeArchived: options?.includeArchived ?? includeArchived })
    setTasks(data.tasks)
    setSelectedTaskId((current) => {
      if (current && data.tasks.some((item) => item.id === current)) {
        return current
      }
      return data.tasks[0]?.id ?? null
    })
    return data.tasks
  }, [includeArchived])

  const refreshGlobalAutoDrive = useCallback(async () => {
    const status = await getGlobalAutoDriveStatus()
    setGlobalAutoDrive(status)
    return status
  }, [])

  const refreshTask = useCallback(async (taskId: string) => {
    setLoading(true)
    try {
      const detail = await getTask(taskId)
      setTask(detail)
      setTaskDraft(toTaskDraft(detail))
      setSelectedRunId((current) => {
        if (current && detail.runs.some((run) => run.id === current)) {
          return current
        }
        return detail.runs.at(-1)?.id ?? null
      })
      return detail
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshArtifacts = useCallback(async (runId: string | null) => {
    if (!runId) {
      setArtifacts([])
      return []
    }
    const data = await getRunArtifacts(runId)
    setArtifacts(data.artifacts)
    return data.artifacts
  }, [])

  useEffect(() => {
    void refreshTasks()
  }, [refreshTasks])

  useEffect(() => {
    void refreshGlobalAutoDrive()
  }, [refreshGlobalAutoDrive])

  useEffect(() => {
    if (!selectedTaskId) {
      setTask(null)
      setTaskDraft(toTaskDraft(null))
      setArtifacts([])
      setPlannedTasks([])
      setPlanSuggestions([])
      return
    }
    void refreshTask(selectedTaskId)
  }, [refreshTask, selectedTaskId])

  useEffect(() => {
    setPlannedTasks([])
    setPlanSuggestions([])
  }, [selectedTaskId])

  useEffect(() => {
    if (!selectedTaskId || !shouldPollTask(task)) {
      return
    }
    const timer = window.setInterval(() => {
      void Promise.all([refreshTask(selectedTaskId), refreshTasks()])
    }, 2000)
    return () => window.clearInterval(timer)
  }, [refreshTask, refreshTasks, selectedTaskId, task])

  useEffect(() => {
    if (!shouldPollGlobalAutoDrive(globalAutoDrive)) {
      return
    }
    const timer = window.setInterval(() => {
      const refreshers: Promise<unknown>[] = [refreshGlobalAutoDrive(), refreshTasks()]
      if (selectedTaskId) {
        refreshers.push(refreshTask(selectedTaskId))
      }
      void Promise.all(refreshers)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [globalAutoDrive, refreshGlobalAutoDrive, refreshTask, refreshTasks, selectedTaskId])

  const handleCreateTask = useCallback(async () => {
    if (!taskPrompt.trim() || creatingTask) {
      return
    }
    setCreatingTask(true)
    try {
      const created = await createTask(inferTaskPayload(taskPrompt))
      await refreshTasks()
      setSelectedTaskId(created.id)
      setTaskPrompt('')
      pushToast({ id: `task-${created.id}`, message: '任务已创建。', tone: 'green' })
    } catch (error) {
      onError(error, '创建任务失败。')
    } finally {
      setCreatingTask(false)
    }
  }, [creatingTask, onError, pushToast, refreshTasks, taskPrompt])

  const handleSaveTask = useCallback(async () => {
    if (!task || savingTask || !taskDraft.title.trim()) {
      return
    }
    setSavingTask(true)
    try {
      await updateTask(task.id, {
        title: taskDraft.title.trim(),
        description: taskDraft.description.trim() || null,
        repoPath: taskDraft.repoPath.trim() || null,
        status: taskDraft.status.trim() || 'open',
        priority: taskDraft.priority.trim() || 'medium',
        labels: parseLabelsText(taskDraft.labelsText),
      })
      await Promise.all([refreshTask(task.id), refreshTasks()])
      pushToast({ id: `task-save-${task.id}`, message: '任务设置已更新。', tone: 'green' })
    } catch (error) {
      onError(error, '更新任务失败。')
    } finally {
      setSavingTask(false)
    }
  }, [onError, pushToast, refreshTask, refreshTasks, savingTask, task, taskDraft])

  const handleAddRef = useCallback(async () => {
    if (!task || addingRef || !refDraft.kind.trim() || !refDraft.label.trim() || !refDraft.value.trim()) {
      return
    }
    setAddingRef(true)
    try {
      await addTaskRef(task.id, refDraft)
      await Promise.all([refreshTask(task.id), refreshTasks()])
      setRefDraft({ kind: 'file', label: '', value: '' })
    } catch (error) {
      onError(error, '添加引用失败。')
    } finally {
      setAddingRef(false)
    }
  }, [addingRef, onError, refDraft, refreshTask, refreshTasks, task])

  const handleDeleteRef = useCallback(async (refId: string) => {
    if (!task) {
      return
    }
    try {
      await deleteTaskRef(task.id, refId)
      await Promise.all([refreshTask(task.id), refreshTasks()])
    } catch (error) {
      onError(error, '删除引用失败。')
    }
  }, [onError, refreshTask, refreshTasks, task])

  const handleCreateSnapshot = useCallback(async () => {
    if (!task || creatingSnapshot) {
      return
    }
    setCreatingSnapshot(true)
    try {
      await resolveTaskContext(task.id, { focus: snapshotFocus || null })
      await Promise.all([refreshTask(task.id), refreshTasks()])
      setSnapshotFocus('')
    } catch (error) {
      onError(error, '生成快照失败。')
    } finally {
      setCreatingSnapshot(false)
    }
  }, [creatingSnapshot, onError, refreshTask, refreshTasks, snapshotFocus, task])

  const executeTaskRun = useCallback(async (
    taskId: string,
    agent: 'codex' | 'claude-code',
    prompt: string,
    options?: { clearPrompt?: boolean },
  ) => {
    const trimmedPrompt = prompt.trim()
    if (creatingRun || !trimmedPrompt) {
      return null
    }
    setCreatingRun(true)
    try {
      const created = await createTaskRun(taskId, { agent, task: trimmedPrompt })
      await Promise.all([refreshTask(taskId), refreshTasks()])
      setSelectedTaskId(taskId)
      setSelectedRunId(created.id)
      setRunAgent(agent)
      setRunPrompt(options?.clearPrompt ? '' : trimmedPrompt)
      setPanelOpen(true)
      return created
    } catch (error) {
      onError(error, '创建 run 失败。')
      return null
    } finally {
      setCreatingRun(false)
    }
  }, [creatingRun, onError, refreshTask, refreshTasks])

  const handleCreateRun = useCallback(async () => {
    if (!task) {
      return
    }
    await executeTaskRun(task.id, runAgent, runPrompt, { clearPrompt: true })
  }, [executeTaskRun, runAgent, runPrompt, task])

  const handleCreateCompare = useCallback(async () => {
    if (!task || task.runs.length < 2 || creatingCompare) {
      return
    }
    setCreatingCompare(true)
    try {
      const latestTwo = task.runs.slice(-2).map((run) => run.id)
      await createTaskCompare(task.id, { runIds: latestTwo, title: `${task.title} · compare` })
      await refreshTask(task.id)
      setPanelOpen(true)
    } catch (error) {
      onError(error, '创建 compare 失败。')
    } finally {
      setCreatingCompare(false)
    }
  }, [creatingCompare, onError, refreshTask, task])

  const handleCreatePlan = useCallback(async () => {
    if (!task || creatingPlan) {
      return
    }
    setCreatingPlan(true)
    try {
      const plan = await planTaskFollowUps(task.id, { createTasks: true, limit: 3 })
      await Promise.all([refreshTasks(), refreshTask(task.id)])
      setPlannedTasks(plan.tasks)
      setPlanSuggestions(plan.suggestions)
      if (plan.tasks.length) {
        pushToast({
          id: `task-plan-${task.id}`,
          message: `KAM 已拆出 ${plan.tasks.length} 个后续任务。`,
          tone: 'green',
        })
      } else {
        pushToast({
          id: `task-plan-${task.id}-noop`,
          message: '当前没有新的后续任务需要拆出。',
          tone: 'amber',
        })
      }
    } catch (error) {
      onError(error, '让 KAM 自己排工作失败。')
    } finally {
      setCreatingPlan(false)
    }
  }, [creatingPlan, onError, pushToast, refreshTask, refreshTasks, task])

  const handleOpenPlannedTask = useCallback((plannedTask: TaskRecord) => {
    const planning = readPlanningMetadata(plannedTask.metadata)
    setSelectedTaskId(plannedTask.id)
    if (planning.recommendedPrompt) {
      setRunPrompt(planning.recommendedPrompt)
      setRunAgent(planning.recommendedAgent)
    }
  }, [])

  const handleRunPlannedTask = useCallback(async (plannedTask: TaskRecord | TaskDetail) => {
    const planning = readPlanningMetadata(plannedTask.metadata)
    if (!planning.recommendedPrompt) {
      pushToast({
        id: `task-plan-run-missing-${plannedTask.id}`,
        message: '这张任务还没有可直接执行的推荐 Prompt。',
        tone: 'amber',
      })
      return
    }
    await executeTaskRun(plannedTask.id, planning.recommendedAgent, planning.recommendedPrompt)
  }, [executeTaskRun, pushToast])

  const handleDispatchNext = useCallback(async () => {
    if (dispatchingNext) {
      return
    }
    setDispatchingNext(true)
    try {
      const dispatched = await dispatchNextTask({ createPlanIfNeeded: true })
      setSelectedTaskId(dispatched.task.id)
      await Promise.all([refreshTasks(), refreshTask(dispatched.task.id)])
      setSelectedRunId(dispatched.run.id)
      setPanelOpen(true)

      const planning = readPlanningMetadata(dispatched.task.metadata)
      if (planning.recommendedPrompt) {
        setRunPrompt(planning.recommendedPrompt)
        setRunAgent(planning.recommendedAgent)
      }

      pushToast({
        id: `dispatch-next-${dispatched.run.id}`,
        message:
          dispatched.source === 'planned_task'
            ? `KAM 已先拆后跑：${dispatched.task.title}`
            : `KAM 已接手下一张任务：${dispatched.task.title}`,
        tone: 'green',
      })
    } catch (error) {
      onError(error, '让 KAM 接下一张任务失败。')
    } finally {
      setDispatchingNext(false)
    }
  }, [dispatchingNext, onError, pushToast, refreshTask, refreshTasks])

  const handleContinueTask = useCallback(async () => {
    if (!task || continuingTask) {
      return
    }
    setContinuingTask(true)
    try {
      const continued = await continueTask({ taskId: task.id, createPlanIfNeeded: true })
      setContinueDecision(continued)
      const nextTaskId = continued.task?.id ?? task.id
      await Promise.all([refreshTasks(), refreshTask(nextTaskId)])
      setSelectedTaskId(nextTaskId)
      if (continued.run) {
        setSelectedRunId(continued.run.id)
        setPanelOpen(true)
      }

      if (continued.task) {
        const planning = readPlanningMetadata(continued.task.metadata)
        if (planning.recommendedPrompt) {
          setRunPrompt(planning.recommendedPrompt)
          setRunAgent(planning.recommendedAgent)
        }
      }

      pushToast({
        id: `task-continue-${Date.now()}`,
        message: continued.summary,
        tone: continued.action === 'stop' ? 'amber' : 'green',
      })
    } catch (error) {
      onError(error, '继续推进当前任务失败。')
    } finally {
      setContinuingTask(false)
    }
  }, [continuingTask, onError, pushToast, refreshTask, refreshTasks, task])

  const handleStartAutoDrive = useCallback(async () => {
    if (!task || managingAutoDrive) {
      return
    }
    setManagingAutoDrive(true)
    try {
      const result = await startTaskAutoDrive(task.id)
      setContinueDecision(null)
      setSelectedTaskId(result.scopeTaskId)
      await Promise.all([refreshTasks(), refreshTask(result.scopeTaskId)])
      pushToast({
        id: `task-autodrive-start-${Date.now()}`,
        message: result.summary,
        tone: 'green',
      })
    } catch (error) {
      onError(error, '开启无人值守失败。')
    } finally {
      setManagingAutoDrive(false)
    }
  }, [managingAutoDrive, onError, pushToast, refreshTask, refreshTasks, task])

  const handleStopAutoDrive = useCallback(async () => {
    if (!task || managingAutoDrive) {
      return
    }
    setManagingAutoDrive(true)
    try {
      const result = await stopTaskAutoDrive(task.id)
      setSelectedTaskId(result.scopeTaskId)
      await Promise.all([refreshTasks(), refreshTask(result.scopeTaskId)])
      pushToast({
        id: `task-autodrive-stop-${Date.now()}`,
        message: result.summary,
        tone: 'amber',
      })
    } catch (error) {
      onError(error, '停止无人值守失败。')
    } finally {
      setManagingAutoDrive(false)
    }
  }, [managingAutoDrive, onError, pushToast, refreshTask, refreshTasks, task])

  const handleStartGlobalAutoDrive = useCallback(async () => {
    if (managingGlobalAutoDrive) {
      return
    }
    setManagingGlobalAutoDrive(true)
    try {
      const result = await startGlobalAutoDrive()
      setContinueDecision(null)
      setGlobalAutoDrive(result)
      const refreshers: Promise<unknown>[] = [refreshGlobalAutoDrive(), refreshTasks()]
      if (selectedTaskId) {
        refreshers.push(refreshTask(selectedTaskId))
      }
      await Promise.all(refreshers)
      pushToast({
        id: `global-autodrive-start-${Date.now()}`,
        message: result.summary,
        tone: 'green',
      })
    } catch (error) {
      onError(error, '开启全局无人值守失败。')
    } finally {
      setManagingGlobalAutoDrive(false)
    }
  }, [managingGlobalAutoDrive, onError, pushToast, refreshGlobalAutoDrive, refreshTask, refreshTasks, selectedTaskId])

  const handleStopGlobalAutoDrive = useCallback(async () => {
    if (managingGlobalAutoDrive) {
      return
    }
    setManagingGlobalAutoDrive(true)
    try {
      const result = await stopGlobalAutoDrive()
      setGlobalAutoDrive(result)
      const refreshers: Promise<unknown>[] = [refreshGlobalAutoDrive(), refreshTasks()]
      if (selectedTaskId) {
        refreshers.push(refreshTask(selectedTaskId))
      }
      await Promise.all(refreshers)
      pushToast({
        id: `global-autodrive-stop-${Date.now()}`,
        message: result.summary,
        tone: 'amber',
      })
    } catch (error) {
      onError(error, '停止全局无人值守失败。')
    } finally {
      setManagingGlobalAutoDrive(false)
    }
  }, [managingGlobalAutoDrive, onError, pushToast, refreshGlobalAutoDrive, refreshTask, refreshTasks, selectedTaskId])

  const handleAdoptRun = useCallback(async (runId: string) => {
    try {
      await adoptRun(runId)
      if (task) {
        await refreshTask(task.id)
      }
    } catch (error) {
      onError(error, '采纳改动失败。')
    }
  }, [onError, refreshTask, task])

  const handleRetryRun = useCallback(async (runId: string) => {
    try {
      const retried = await retryRun(runId)
      if (task) {
        await refreshTask(task.id)
      }
      setSelectedRunId(retried.id)
    } catch (error) {
      onError(error, '重试执行失败。')
    }
  }, [onError, refreshTask, task])

  const handleArchiveTask = useCallback(async () => {
    if (!task) {
      return
    }
    try {
      await archiveTask(task.id)
      setIncludeArchived(true)
      await refreshTasks({ includeArchived: true })
      setSelectedTaskId(task.id)
      await refreshTask(task.id)
      pushToast({ id: `task-archive-${task.id}`, message: '任务已归档。', tone: 'green' })
    } catch (error) {
      onError(error, '归档任务失败。')
    }
  }, [onError, pushToast, refreshTask, refreshTasks, task])

  const selectedRun = useMemo(
    () => task?.runs.find((item) => item.id === selectedRunId) ?? task?.runs.at(-1) ?? null,
    [selectedRunId, task],
  )
  const autoDriveEnabled = useMemo(() => parseAutoDriveEnabled(task?.metadata.autoDriveEnabled), [task])
  const globalAutoDriveEnabled = useMemo(() => globalAutoDrive?.enabled === true, [globalAutoDrive])
  const globalCurrentTaskTitle = useMemo(() => {
    if (!globalAutoDrive?.currentTaskId) {
      return null
    }
    return tasks.find((item) => item.id === globalAutoDrive.currentTaskId)?.title ?? globalAutoDrive.currentTaskId
  }, [globalAutoDrive, tasks])
  const globalScopeTaskTitle = useMemo(() => {
    if (!globalAutoDrive?.currentScopeTaskId) {
      return null
    }
    return tasks.find((item) => item.id === globalAutoDrive.currentScopeTaskId)?.title ?? globalAutoDrive.currentScopeTaskId
  }, [globalAutoDrive, tasks])

  const breadcrumb = useMemo(() => (task ? `Tasks / ${task.title}` : 'Tasks'), [task])
  const selectedRunLabel = useMemo(() => {
    return selectedRun ? `${selectedRun.agent} · ${selectedRun.status}` : ''
  }, [selectedRun])

  useEffect(() => {
    void refreshArtifacts(selectedRun?.id ?? null)
  }, [refreshArtifacts, selectedRun?.id, selectedRun?.resultSummary, selectedRun?.status])

  return (
    <AppShell
      sidebar={
        <TaskSidebar
          tasks={tasks}
          activeTaskId={selectedTaskId}
          includeArchived={includeArchived}
          onSelectTask={setSelectedTaskId}
          onCreateTask={() => setSelectedTaskId(null)}
          onToggleArchived={() => setIncludeArchived((current) => !current)}
        />
      }
      breadcrumb={breadcrumb}
      memoryOpen={panelOpen}
      onToggleMemory={() => setPanelOpen((current) => !current)}
      panelToggleLabel="详情"
      toasts={toasts}
      panel={<TaskPanel artifacts={artifacts} snapshots={task?.snapshots ?? []} reviews={task?.reviews ?? []} selectedRunLabel={selectedRunLabel} />}
      main={
        <div className="task-main-shell">
          <section className="feed-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">全局无人值守</div>
                <div className="feed-card-subtle">{globalAutoDrive?.summary ?? '当前还没有开启全局无人值守。'}</div>
              </div>
              <button
                type="button"
                className="button-secondary"
                disabled={managingGlobalAutoDrive}
                onClick={globalAutoDriveEnabled ? handleStopGlobalAutoDrive : handleStartGlobalAutoDrive}
              >
                {managingGlobalAutoDrive
                  ? globalAutoDriveEnabled
                    ? '停止中…'
                    : '启动中…'
                  : globalAutoDriveEnabled
                    ? '停止全局无人值守'
                    : '开启全局无人值守'}
              </button>
            </div>
            <div className="task-chip-row">
              <span className="file-chip">状态 · {globalAutoDriveEnabled ? '已开启' : '未开启'}</span>
              {globalAutoDrive?.status ? <span className="file-chip">阶段 · {autoDriveStatusLabel(globalAutoDrive.status)}</span> : null}
              {globalAutoDrive?.lastAction ? <span className="file-chip">动作 · {globalAutoDrive.lastAction}</span> : null}
              {globalAutoDrive?.lastReason ? (
                <span className="file-chip">原因 · {autoDriveReasonLabel(globalAutoDrive.lastReason)}</span>
              ) : null}
              {typeof globalAutoDrive?.loopCount === 'number' ? <span className="file-chip">轮次 · {globalAutoDrive.loopCount}</span> : null}
            </div>
            {globalCurrentTaskTitle || globalScopeTaskTitle || globalAutoDrive?.currentRunId || globalAutoDrive?.error ? (
              <div className="task-chip-row">
                {globalCurrentTaskTitle ? <span className="file-chip">当前任务 · {globalCurrentTaskTitle}</span> : null}
                {globalScopeTaskTitle ? <span className="file-chip">当前 scope · {globalScopeTaskTitle}</span> : null}
                {globalAutoDrive?.currentRunId ? <span className="file-chip">当前 Run · {globalAutoDrive.currentRunId}</span> : null}
                {globalAutoDrive?.error ? <span className="file-chip">错误 · {globalAutoDrive.error}</span> : null}
              </div>
            ) : null}
          </section>

          {selectedTaskId ? (
            <>
            <div className="task-main-actions">
              <button type="button" className="button-primary" disabled={dispatchingNext} onClick={handleDispatchNext}>
                {dispatchingNext ? 'KAM 接任务中…' : '让 KAM 接下一张'}
              </button>
              {task ? (
                <button
                  type="button"
                  className="button-secondary"
                  disabled={managingAutoDrive}
                  onClick={autoDriveEnabled ? handleStopAutoDrive : handleStartAutoDrive}
                >
                  {managingAutoDrive ? (autoDriveEnabled ? '停止中…' : '启动中…') : autoDriveEnabled ? '停止无人值守' : '进入无人值守'}
                </button>
              ) : null}
              {task ? (
                <button type="button" className="button-secondary" disabled={continuingTask} onClick={handleContinueTask}>
                  {continuingTask ? 'KAM 推进中…' : '继续推进当前任务'}
                </button>
              ) : null}
              <button type="button" className="button-secondary" onClick={() => setSelectedTaskId(null)}>
                新建任务
              </button>
              {task ? (
                <button type="button" className="button-secondary" onClick={handleArchiveTask}>
                  归档任务
                </button>
              ) : null}
            </div>
            <TaskWorkbench
              task={task}
              taskDraft={taskDraft}
              loading={loading}
              runPrompt={runPrompt}
              runAgent={runAgent}
              refDraft={refDraft}
              snapshotFocus={snapshotFocus}
              selectedRunId={selectedRunId}
              creatingRun={creatingRun}
              addingRef={addingRef}
              creatingSnapshot={creatingSnapshot}
              creatingCompare={creatingCompare}
              creatingPlan={creatingPlan}
              continueDecision={continueDecision}
              savingTask={savingTask}
              plannedTasks={plannedTasks}
              planSuggestions={planSuggestions}
              onRunPromptChange={setRunPrompt}
              onRunAgentChange={setRunAgent}
              onTaskDraftChange={setTaskDraft}
              onSaveTask={handleSaveTask}
              onCreatePlan={handleCreatePlan}
              onRunRecommendedTask={() => {
                if (task) {
                  void handleRunPlannedTask(task)
                }
              }}
              onCreateRun={handleCreateRun}
              onRefDraftChange={setRefDraft}
              onAddRef={handleAddRef}
              onDeleteRef={handleDeleteRef}
              onSnapshotFocusChange={setSnapshotFocus}
              onCreateSnapshot={handleCreateSnapshot}
              onCreateCompare={handleCreateCompare}
              onSelectRun={(runId) => {
                setSelectedRunId(runId)
                setPanelOpen(true)
              }}
              onOpenPlannedTask={handleOpenPlannedTask}
              onRunPlannedTask={handleRunPlannedTask}
              onAdoptRun={handleAdoptRun}
              onRetryRun={handleRetryRun}
            />
            </>
          ) : (
            <EmptyTaskState value={taskPrompt} onChange={setTaskPrompt} onSubmit={handleCreateTask} isBusy={creatingTask} />
          )}
        </div>
      }
    />
  )
}

export default App
