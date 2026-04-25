import { useCallback, useEffect, useRef, useState } from 'react'

import {
  deleteIssueMonitorRecord,
  getOperatorControlPlane,
  performOperatorAction,
  runIssueMonitorOnce,
  upsertIssueMonitor,
} from '@/api/client'
import type { ToastItem } from '@/layout/Toast'
import type {
  OperatorActionKey,
  OperatorActionRecord,
  OperatorControlPlaneResponse,
  TaskContinueResponse,
  TaskDetail,
  TaskRecord,
} from '@/types/harness'

type IssueMonitorDraft = {
  repo: string
  repoPath: string
}

export type UseOperatorParams = {
  selectedTaskId: string | null
  setSelectedTaskId: (id: string | null) => void
  refreshTasks: (options?: { includeArchived?: boolean }) => Promise<TaskRecord[]>
  refreshTask: (taskId: string) => Promise<TaskDetail>
  setSelectedRunId: (id: string | null) => void
  pushToast: (toast: ToastItem) => void
  onError: (error: unknown, fallback: string) => void
  taskDependencyReady: boolean | undefined
  taskDependencySummary: string | null | undefined
  taskUpdatedAt: string | undefined
}

export function useOperator({
  selectedTaskId,
  setSelectedTaskId,
  refreshTasks,
  refreshTask,
  setSelectedRunId,
  pushToast,
  onError,
  taskDependencyReady,
  taskDependencySummary,
  taskUpdatedAt,
}: UseOperatorParams) {
  const operatorRefreshSeqRef = useRef(0)
  const [operatorControl, setOperatorControl] = useState<OperatorControlPlaneResponse | null>(null)
  const [operatorActionPending, setOperatorActionPending] = useState<OperatorActionKey | null>(null)
  const [refreshingOperatorControl, setRefreshingOperatorControl] = useState(false)
  const [issueMonitorDraft, setIssueMonitorDraft] = useState<IssueMonitorDraft>({ repo: '', repoPath: '' })
  const [issueMonitorPending, setIssueMonitorPending] = useState<string | null>(null)
  const [continueDecision, setContinueDecision] = useState<TaskContinueResponse | null>(null)

  const refreshOperatorControl = useCallback(
    async (taskId?: string | null) => {
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
    },
    [selectedTaskId],
  )

  // Initial load
  useEffect(() => {
    void refreshOperatorControl()
  }, [refreshOperatorControl])

  // Refresh operator when selectedTaskId or task dependency state changes
  useEffect(() => {
    if (!selectedTaskId) {
      return
    }
    void refreshOperatorControl(selectedTaskId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshOperatorControl, selectedTaskId, taskDependencyReady, taskDependencySummary, taskUpdatedAt])

  const globalAutoDrive = operatorControl?.globalAutoDrive ?? null

  // 2-second polling when global auto-drive is enabled
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

  const handleOperatorAction = useCallback(
    async (action: OperatorActionRecord) => {
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
          tone:
            action.key === 'cancel_run'
              ? 'amber'
              : action.tone === 'red'
                ? 'red'
                : action.tone === 'gray'
                  ? 'amber'
                  : 'green',
        })
      } catch (error) {
        onError(error, '执行 operator 动作失败。')
      } finally {
        setOperatorActionPending(null)
      }
    },
    [onError, operatorActionPending, pushToast, refreshTask, refreshTasks, selectedTaskId, setSelectedRunId, setSelectedTaskId],
  )

  const handleSaveIssueMonitor = useCallback(async () => {
    const repo = issueMonitorDraft.repo.trim()
    if (!repo || issueMonitorPending) {
      return
    }
    setIssueMonitorPending('register')
    try {
      const monitor = await upsertIssueMonitor({
        repo,
        repoPath: issueMonitorDraft.repoPath.trim() || null,
        runNow: true,
      })
      const nextTaskId = monitor.taskIds[0] ?? selectedTaskId
      const refreshers: Promise<unknown>[] = [refreshTasks(), refreshOperatorControl(nextTaskId)]
      if (nextTaskId) {
        setSelectedTaskId(nextTaskId)
        refreshers.push(refreshTask(nextTaskId))
      }
      await Promise.all(refreshers)
      pushToast({
        id: `issue-monitor-register-${repo}-${Date.now()}`,
        message: `已注册 GitHub Issue 自动入池：${monitor.repo}`,
        tone: 'green',
      })
    } catch (error) {
      onError(error, '注册 GitHub Issue 自动入池失败。')
    } finally {
      setIssueMonitorPending(null)
    }
  }, [issueMonitorDraft.repo, issueMonitorDraft.repoPath, issueMonitorPending, onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, selectedTaskId, setSelectedTaskId])

  const handleRunIssueMonitor = useCallback(
    async (repo: string) => {
      if (!repo.trim() || issueMonitorPending) {
        return
      }
      setIssueMonitorPending(`run:${repo}`)
      try {
        const result = await runIssueMonitorOnce(repo)
        const nextTaskId = result.taskIds[0] ?? selectedTaskId
        const refreshers: Promise<unknown>[] = [refreshTasks(), refreshOperatorControl(nextTaskId)]
        if (nextTaskId) {
          setSelectedTaskId(nextTaskId)
          refreshers.push(refreshTask(nextTaskId))
        }
        await Promise.all(refreshers)
        pushToast({
          id: `issue-monitor-run-${repo}-${Date.now()}`,
          message: result.message,
          tone:
            result.status === 'failed' || result.status === 'source-error'
              ? 'red'
              : result.status === 'enqueued'
                ? 'green'
                : 'amber',
        })
      } catch (error) {
        onError(error, '手动重扫 GitHub Issue 失败。')
      } finally {
        setIssueMonitorPending(null)
      }
    },
    [issueMonitorPending, onError, pushToast, refreshOperatorControl, refreshTask, refreshTasks, selectedTaskId, setSelectedTaskId],
  )

  const handleDeleteIssueMonitor = useCallback(
    async (repo: string) => {
      if (!repo.trim() || issueMonitorPending) {
        return
      }
      setIssueMonitorPending(`remove:${repo}`)
      try {
        await deleteIssueMonitorRecord(repo)
        await refreshOperatorControl(selectedTaskId)
        pushToast({
          id: `issue-monitor-remove-${repo}-${Date.now()}`,
          message: `已移除 GitHub Issue 自动入池：${repo}`,
          tone: 'green',
        })
      } catch (error) {
        onError(error, '移除 GitHub Issue 自动入池失败。')
      } finally {
        setIssueMonitorPending(null)
      }
    },
    [issueMonitorPending, onError, pushToast, refreshOperatorControl, selectedTaskId],
  )

  return {
    operatorControl,
    operatorActionPending,
    refreshingOperatorControl,
    issueMonitorDraft,
    setIssueMonitorDraft,
    issueMonitorPending,
    continueDecision,
    refreshOperatorControl,
    handleOperatorAction,
    handleSaveIssueMonitor,
    handleRunIssueMonitor,
    handleDeleteIssueMonitor,
  }
}
