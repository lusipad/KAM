import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  addTaskRef,
  addTaskDependency,
  adoptRun,
  archiveTask,
  cancelRun,
  createTaskCompare,
  createTaskRun,
  deleteTaskRef,
  deleteTaskDependency,
  getRunArtifacts,
  getTask,
  planTaskFollowUps,
  resolveTaskContext,
  retryRun,
  updateTask,
} from '@/api/client'
import { taskShouldPoll } from '@/features/tasks/taskMetadata'
import type { ToastItem } from '@/layout/Toast'
import type {
  RunArtifactRecord,
  TaskDetail,
  TaskPlanSuggestion,
  TaskRecord,
} from '@/types/harness'

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
    return { title: '', description: '', repoPath: '', status: 'open', priority: 'medium', labelsText: '' }
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

export type UseTaskSessionParams = {
  selectedTaskId: string | null
  setSelectedTaskId: (id: string | null) => void
  refreshTasks: (options?: { includeArchived?: boolean }) => Promise<TaskRecord[]>
  pushToast: (toast: ToastItem) => void
  onError: (error: unknown, fallback: string) => void
  refreshOperatorControl: (taskId?: string | null) => Promise<unknown>
}

export function useTaskSession({
  selectedTaskId,
  setSelectedTaskId,
  refreshTasks,
  pushToast,
  onError,
  refreshOperatorControl,
}: UseTaskSessionParams) {
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [taskDraft, setTaskDraft] = useState<TaskDraft>(toTaskDraft(null))
  const [loading, setLoading] = useState(false)
  const [artifacts, setArtifacts] = useState<RunArtifactRecord[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [runPrompt, setRunPrompt] = useState('')
  const [runAgent, setRunAgent] = useState<'codex' | 'claude-code'>('codex')
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

  // Clear / reload on selectedTaskId change
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

  // Clear plan states on task switch
  useEffect(() => {
    setPlannedTasks([])
    setPlanSuggestions([])
    setDependencyDraft('')
  }, [selectedTaskId])

  // 2-second polling when task has active runs
  useEffect(() => {
    if (!selectedTaskId || !taskShouldPoll(task)) {
      return
    }
    const timer = window.setInterval(() => {
      void Promise.all([refreshTask(selectedTaskId), refreshTasks(), refreshOperatorControl(selectedTaskId)])
    }, 2000)
    return () => window.clearInterval(timer)
  }, [refreshOperatorControl, refreshTask, refreshTasks, selectedTaskId, task])

  const selectedRun = useMemo(
    () => task?.runs.find((item) => item.id === selectedRunId) ?? task?.runs.at(-1) ?? null,
    [selectedRunId, task],
  )
  const taskBlocked = useMemo(() => task?.dependencyState?.ready === false, [task])
  const selectedRunLabel = useMemo(
    () => (selectedRun ? `${selectedRun.agent} · ${selectedRun.status}` : ''),
    [selectedRun],
  )

  // Refresh artifacts when selected run changes
  useEffect(() => {
    void refreshArtifacts(selectedRun?.id ?? null)
  }, [refreshArtifacts, selectedRun?.id, selectedRun?.resultSummary, selectedRun?.status])

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

  const handleDeleteRef = useCallback(
    async (refId: string) => {
      if (!task) {
        return
      }
      try {
        await deleteTaskRef(task.id, refId)
        await Promise.all([refreshTask(task.id), refreshTasks()])
      } catch (error) {
        onError(error, '删除引用失败。')
      }
    },
    [onError, refreshTask, refreshTasks, task],
  )

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

  const handleDeleteDependency = useCallback(
    async (dependsOnTaskId: string) => {
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
    },
    [onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, task],
  )

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

  const executeTaskRun = useCallback(
    async (
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
        return created
      } catch (error) {
        onError(error, '创建 run 失败。')
        return null
      } finally {
        setCreatingRun(false)
      }
    },
    [creatingRun, onError, refreshTask, refreshTasks, setSelectedTaskId],
  )

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
      pushToast({
        id: `task-plan-${task.id}`,
        message: plan.tasks.length
          ? `KAM 已拆出 ${plan.tasks.length} 个后续任务。`
          : '当前没有新的后续任务需要拆出。',
        tone: plan.tasks.length ? 'green' : 'amber',
      })
    } catch (error) {
      onError(error, '让 KAM 自己排工作失败。')
    } finally {
      setCreatingPlan(false)
    }
  }, [creatingPlan, onError, pushToast, refreshTask, refreshTasks, task])

  const handleOpenPlannedTask = useCallback(
    (plannedTask: TaskRecord) => {
      const meta = plannedTask.metadata || {}
      const recommendedPrompt = typeof meta.recommendedPrompt === 'string' ? meta.recommendedPrompt : null
      const recommendedAgent = meta.recommendedAgent === 'claude-code' ? ('claude-code' as const) : ('codex' as const)
      setSelectedTaskId(plannedTask.id)
      if (recommendedPrompt) {
        setRunPrompt(recommendedPrompt)
        setRunAgent(recommendedAgent)
      }
    },
    [setSelectedTaskId],
  )

  const handleRunPlannedTask = useCallback(
    async (plannedTask: TaskRecord | TaskDetail) => {
      const meta = plannedTask.metadata || {}
      const recommendedPrompt = typeof meta.recommendedPrompt === 'string' ? meta.recommendedPrompt : null
      if (!recommendedPrompt) {
        pushToast({
          id: `task-plan-run-missing-${plannedTask.id}`,
          message: '这张任务还没有可直接执行的推荐 Prompt。',
          tone: 'amber',
        })
        return
      }
      const recommendedAgent = meta.recommendedAgent === 'claude-code' ? ('claude-code' as const) : ('codex' as const)
      await executeTaskRun(plannedTask.id, recommendedAgent, recommendedPrompt)
    },
    [executeTaskRun, pushToast],
  )

  const handleAdoptRun = useCallback(
    async (runId: string) => {
      try {
        await adoptRun(runId)
        if (task) {
          await refreshTask(task.id)
        }
      } catch (error) {
        onError(error, '采纳改动失败。')
      }
    },
    [onError, refreshTask, task],
  )

  const handleRetryRun = useCallback(
    async (runId: string) => {
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
    },
    [onError, refreshOperatorControl, refreshTask, task],
  )

  const handleCancelRun = useCallback(
    async (runId: string) => {
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
    },
    [onError, pushToast, refreshOperatorControl, refreshTask, task],
  )

  const handleArchiveTask = useCallback(async () => {
    if (!task) {
      return
    }
    try {
      await archiveTask(task.id)
      await refreshTasks({ includeArchived: true })
      setSelectedTaskId(task.id)
      await Promise.all([refreshTask(task.id), refreshOperatorControl(task.id)])
      pushToast({ id: `task-archive-${task.id}`, message: '任务已归档。', tone: 'green' })
    } catch (error) {
      onError(error, '归档任务失败。')
    }
  }, [onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, setSelectedTaskId, task])

  return {
    task,
    taskDraft,
    setTaskDraft,
    loading,
    artifacts,
    selectedRunId,
    setSelectedRunId,
    runPrompt,
    setRunPrompt,
    runAgent,
    setRunAgent,
    refDraft,
    setRefDraft,
    dependencyDraft,
    setDependencyDraft,
    snapshotFocus,
    setSnapshotFocus,
    plannedTasks,
    planSuggestions,
    creatingRun,
    addingRef,
    creatingSnapshot,
    creatingCompare,
    creatingPlan,
    addingDependency,
    savingTask,
    selectedRun,
    taskBlocked,
    selectedRunLabel,
    refreshTask,
    handleSaveTask,
    handleAddRef,
    handleDeleteRef,
    handleAddDependency,
    handleDeleteDependency,
    handleCreateSnapshot,
    executeTaskRun,
    handleCreateRun,
    handleCreateCompare,
    handleCreatePlan,
    handleOpenPlannedTask,
    handleRunPlannedTask,
    handleAdoptRun,
    handleRetryRun,
    handleCancelRun,
    handleArchiveTask,
  }
}
