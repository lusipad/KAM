import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  addTaskRef,
  addTaskDependency,
  adoptRun,
  archiveTask,
  cancelRun,
  createTask,
  createTaskCompare,
  createTaskRun,
  deleteTaskRef,
  deleteTaskDependency,
  getErrorMessage,
  getOperatorControlPlane,
  getRunArtifacts,
  getTask,
  listTasks,
  planTaskFollowUps,
  performOperatorAction,
  resolveTaskContext,
  retryRun,
  updateTask,
} from '@/api/client'
import { OperatorPanel } from '@/features/operator/OperatorPanel'
import { readPlanningMetadata, taskShouldPoll } from '@/features/tasks/taskMetadata'
import { TaskPanel } from '@/features/tasks/TaskPanel'
import { TaskSidebar } from '@/features/tasks/TaskSidebar'
import { TaskWorkbench } from '@/features/tasks/TaskWorkbench'
import { AppShell } from '@/layout/AppShell'
import type { ToastItem } from '@/layout/Toast'
import type {
  OperatorActionKey,
  OperatorActionRecord,
  OperatorControlPlaneResponse,
  RunArtifactRecord,
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
  const operatorRefreshSeqRef = useRef(0)
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
  const [addingDependency, setAddingDependency] = useState(false)
  const [savingTask, setSavingTask] = useState(false)
  const [snapshotFocus, setSnapshotFocus] = useState('')
  const [refDraft, setRefDraft] = useState({ kind: 'file', label: '', value: '' })
  const [dependencyDraft, setDependencyDraft] = useState('')
  const [plannedTasks, setPlannedTasks] = useState<TaskRecord[]>([])
  const [planSuggestions, setPlanSuggestions] = useState<TaskPlanSuggestion[]>([])
  const [continueDecision, setContinueDecision] = useState<TaskContinueResponse | null>(null)
  const [operatorControl, setOperatorControl] = useState<OperatorControlPlaneResponse | null>(null)
  const [operatorActionPending, setOperatorActionPending] = useState<OperatorActionKey | null>(null)
  const [refreshingOperatorControl, setRefreshingOperatorControl] = useState(false)
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

  const refreshOperatorControl = useCallback(async (taskId?: string | null) => {
    const requestId = operatorRefreshSeqRef.current + 1
    operatorRefreshSeqRef.current = requestId
    setRefreshingOperatorControl(true)
    try {
      const controlPlane = await getOperatorControlPlane(taskId ?? selectedTaskId)
      if (requestId === operatorRefreshSeqRef.current) {
        setOperatorControl(controlPlane)
      }
      return controlPlane
    } finally {
      if (requestId === operatorRefreshSeqRef.current) {
        setRefreshingOperatorControl(false)
      }
    }
  }, [selectedTaskId])

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
    void refreshOperatorControl()
  }, [refreshOperatorControl])

  useEffect(() => {
    if (!selectedTaskId) {
      return
    }
    void refreshOperatorControl(selectedTaskId)
  }, [refreshOperatorControl, selectedTaskId, task?.dependencyState?.ready, task?.dependencyState?.summary, task?.updatedAt])

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
    setDependencyDraft('')
  }, [selectedTaskId])

  useEffect(() => {
    if (!selectedTaskId || !taskShouldPoll(task)) {
      return
    }
    const timer = window.setInterval(() => {
      void Promise.all([refreshTask(selectedTaskId), refreshTasks(), refreshOperatorControl(selectedTaskId)])
    }, 2000)
    return () => window.clearInterval(timer)
  }, [refreshOperatorControl, refreshTask, refreshTasks, selectedTaskId, task])

  const globalAutoDrive = operatorControl?.globalAutoDrive ?? null

  useEffect(() => {
    if (!globalAutoDrive || (!globalAutoDrive.enabled && !globalAutoDrive.running)) {
      return
    }
    const timer = window.setInterval(() => {
      const refreshers: Promise<unknown>[] = [refreshTasks(), refreshOperatorControl(selectedTaskId)]
      if (selectedTaskId) {
        refreshers.push(refreshTask(selectedTaskId))
      }
      void Promise.all(refreshers)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [globalAutoDrive, refreshOperatorControl, refreshTask, refreshTasks, selectedTaskId])

  const handleOperatorAction = useCallback(async (action: OperatorActionRecord) => {
    if (operatorActionPending) {
      return
    }
    setOperatorActionPending(action.key)
    try {
      const result = await performOperatorAction({
        action: action.key,
        taskId: action.taskId ?? selectedTaskId,
        runId: action.runId,
      })
      operatorRefreshSeqRef.current += 1
      setOperatorControl(result.controlPlane)
      setRefreshingOperatorControl(false)
      setContinueDecision(result.continueDecision ?? null)
      if (result.taskId) {
        setSelectedTaskId(result.taskId)
      }
      if (result.runId) {
        setSelectedRunId(result.runId)
      }

      const focusTaskId = result.taskId ?? selectedTaskId
      const refreshers: Promise<unknown>[] = [refreshTasks()]
      if (focusTaskId) {
        refreshers.push(refreshTask(focusTaskId))
      }
      await Promise.all(refreshers)
      pushToast({
        id: `operator-action-${action.key}-${Date.now()}`,
        message: result.summary,
        tone: action.key === 'cancel_run' ? 'amber' : action.tone === 'red' ? 'red' : action.tone === 'gray' ? 'amber' : 'green',
      })
    } catch (error) {
      onError(error, '执行 operator 动作失败。')
    } finally {
      setOperatorActionPending(null)
    }
  }, [onError, operatorActionPending, pushToast, refreshTask, refreshTasks, selectedTaskId])

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
      await Promise.all([refreshTask(task.id), refreshTasks(), refreshOperatorControl(task.id)])
      pushToast({ id: `task-save-${task.id}`, message: '任务设置已更新。', tone: 'green' })
    } catch (error) {
      onError(error, '更新任务失败。')
    } finally {
      setSavingTask(false)
    }
  }, [onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, savingTask, task, taskDraft])

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

  const handleAddDependency = useCallback(async () => {
    if (!task || addingDependency || !dependencyDraft.trim()) {
      return
    }
    setAddingDependency(true)
    try {
      await addTaskDependency(task.id, { dependsOnTaskId: dependencyDraft.trim() })
      await Promise.all([refreshTask(task.id), refreshTasks(), refreshOperatorControl(task.id)])
      setDependencyDraft('')
      pushToast({ id: `task-dependency-add-${Date.now()}`, message: '依赖已添加。', tone: 'green' })
    } catch (error) {
      onError(error, '添加依赖失败。')
    } finally {
      setAddingDependency(false)
    }
  }, [addingDependency, dependencyDraft, onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, task])

  const handleDeleteDependency = useCallback(async (dependsOnTaskId: string) => {
    if (!task) {
      return
    }
    try {
      await deleteTaskDependency(task.id, dependsOnTaskId)
      await Promise.all([refreshTask(task.id), refreshTasks(), refreshOperatorControl(task.id)])
      pushToast({ id: `task-dependency-delete-${Date.now()}`, message: '依赖已移除。', tone: 'green' })
    } catch (error) {
      onError(error, '移除依赖失败。')
    }
  }, [onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, task])

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
      await refreshOperatorControl(task?.id ?? retried.taskId)
      setSelectedRunId(retried.id)
    } catch (error) {
      onError(error, '重试执行失败。')
    }
  }, [onError, refreshOperatorControl, refreshTask, task])

  const handleCancelRun = useCallback(async (runId: string) => {
    try {
      const cancelled = await cancelRun(runId)
      if (task) {
        await refreshTask(task.id)
      }
      await refreshOperatorControl(task?.id ?? cancelled.taskId)
      setSelectedRunId(cancelled.id)
      pushToast({ id: `task-cancel-${runId}`, message: '当前 run 已打断。', tone: 'amber' })
    } catch (error) {
      onError(error, '打断执行失败。')
    }
  }, [onError, pushToast, refreshOperatorControl, refreshTask, task])

  const handleArchiveTask = useCallback(async () => {
    if (!task) {
      return
    }
    try {
      await archiveTask(task.id)
      setIncludeArchived(true)
      await refreshTasks({ includeArchived: true })
      setSelectedTaskId(task.id)
      await Promise.all([refreshTask(task.id), refreshOperatorControl(task.id)])
      pushToast({ id: `task-archive-${task.id}`, message: '任务已归档。', tone: 'green' })
    } catch (error) {
      onError(error, '归档任务失败。')
    }
  }, [onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, task])

  const selectedRun = useMemo(
    () => task?.runs.find((item) => item.id === selectedRunId) ?? task?.runs.at(-1) ?? null,
    [selectedRunId, task],
  )
  const taskBlocked = useMemo(() => task?.dependencyState?.ready === false, [task])

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
          <OperatorPanel
            controlPlane={operatorControl}
            actionPending={operatorActionPending}
            refreshing={refreshingOperatorControl}
            selectedTaskBlockedReason={taskBlocked ? task?.dependencyState?.summary ?? '当前任务仍被依赖阻塞。' : null}
            onRefresh={() => {
              void refreshOperatorControl()
            }}
            onAction={(action) => {
              void handleOperatorAction(action)
            }}
            onSelectTask={setSelectedTaskId}
          />

          {selectedTaskId ? (
            <>
            <div className="task-main-actions">
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
              dependencyDraft={dependencyDraft}
              snapshotFocus={snapshotFocus}
              selectedRunId={selectedRunId}
              creatingRun={creatingRun}
              addingRef={addingRef}
              addingDependency={addingDependency}
              creatingSnapshot={creatingSnapshot}
              creatingCompare={creatingCompare}
              creatingPlan={creatingPlan}
              continueDecision={continueDecision}
              savingTask={savingTask}
              taskBlocked={taskBlocked}
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
              onDependencyDraftChange={setDependencyDraft}
              onAddDependency={handleAddDependency}
              onDeleteDependency={handleDeleteDependency}
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
              onCancelRun={handleCancelRun}
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
