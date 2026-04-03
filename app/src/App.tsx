import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  addTaskRef,
  adoptRun,
  archiveTask,
  createTask,
  createTaskCompare,
  createTaskRun,
  deleteTaskRef,
  getErrorMessage,
  getRunArtifacts,
  getTask,
  listTasks,
  resolveTaskContext,
  retryRun,
} from '@/api/client'
import { TaskPanel } from '@/features/tasks/TaskPanel'
import { TaskSidebar } from '@/features/tasks/TaskSidebar'
import { TaskWorkbench } from '@/features/tasks/TaskWorkbench'
import { AppShell } from '@/layout/AppShell'
import type { ToastItem } from '@/layout/Toast'
import type { RunArtifactRecord, TaskDetail, TaskRecord } from '@/types/v3'

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
  const [loading, setLoading] = useState(false)
  const [panelOpen, setPanelOpen] = useState(true)
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
  const [snapshotFocus, setSnapshotFocus] = useState('')
  const [refDraft, setRefDraft] = useState({ kind: 'file', label: '', value: '' })
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

  const refreshTasks = useCallback(async () => {
    const data = await listTasks()
    setTasks(data.tasks)
    setSelectedTaskId((current) => {
      if (current && data.tasks.some((item) => item.id === current)) {
        return current
      }
      return data.tasks[0]?.id ?? null
    })
    return data.tasks
  }, [])

  const refreshTask = useCallback(async (taskId: string) => {
    setLoading(true)
    try {
      const detail = await getTask(taskId)
      setTask(detail)
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
    if (!selectedTaskId) {
      setTask(null)
      setArtifacts([])
      return
    }
    void refreshTask(selectedTaskId)
  }, [refreshTask, selectedTaskId])

  useEffect(() => {
    if (!selectedTaskId || !task?.runs.some((run) => run.status === 'pending' || run.status === 'running')) {
      return
    }
    const timer = window.setInterval(() => {
      void refreshTask(selectedTaskId)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [refreshTask, selectedTaskId, task?.runs])

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

  const handleCreateRun = useCallback(async () => {
    if (!task || creatingRun || !runPrompt.trim()) {
      return
    }
    setCreatingRun(true)
    try {
      const created = await createTaskRun(task.id, { agent: runAgent, task: runPrompt.trim() })
      await Promise.all([refreshTask(task.id), refreshTasks()])
      setSelectedRunId(created.id)
      setRunPrompt('')
      setPanelOpen(true)
    } catch (error) {
      onError(error, '创建 run 失败。')
    } finally {
      setCreatingRun(false)
    }
  }, [creatingRun, onError, refreshTask, refreshTasks, runAgent, runPrompt, task])

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
      await refreshTasks()
      setTask(null)
      setArtifacts([])
    } catch (error) {
      onError(error, '归档任务失败。')
    }
  }, [onError, refreshTasks, task])

  const selectedRun = useMemo(
    () => task?.runs.find((item) => item.id === selectedRunId) ?? task?.runs.at(-1) ?? null,
    [selectedRunId, task],
  )

  const breadcrumb = useMemo(() => (task ? `Tasks / ${task.title}` : 'Tasks'), [task])
  const selectedRunLabel = useMemo(() => {
    return selectedRun ? `${selectedRun.agent} · ${selectedRun.status}` : ''
  }, [selectedRun])

  useEffect(() => {
    void refreshArtifacts(selectedRun?.id ?? null)
  }, [refreshArtifacts, selectedRun?.id, selectedRun?.resultSummary, selectedRun?.status])

  return (
    <AppShell
      sidebar={<TaskSidebar tasks={tasks} activeTaskId={selectedTaskId} onSelectTask={setSelectedTaskId} onCreateTask={() => setSelectedTaskId(null)} />}
      breadcrumb={breadcrumb}
      memoryOpen={panelOpen}
      onToggleMemory={() => setPanelOpen((current) => !current)}
      panelToggleLabel="详情"
      toasts={toasts}
      panel={<TaskPanel artifacts={artifacts} snapshots={task?.snapshots ?? []} reviews={task?.reviews ?? []} selectedRunLabel={selectedRunLabel} />}
      main={
        selectedTaskId ? (
          <div className="task-main-shell">
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
              onRunPromptChange={setRunPrompt}
              onRunAgentChange={setRunAgent}
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
              onAdoptRun={handleAdoptRun}
              onRetryRun={handleRetryRun}
            />
          </div>
        ) : (
          <EmptyTaskState value={taskPrompt} onChange={setTaskPrompt} onSubmit={handleCreateTask} isBusy={creatingTask} />
        )
      }
    />
  )
}

export default App
