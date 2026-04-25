import { useCallback, useEffect, useState } from 'react'

import { createTask, listTasks } from '@/api/client'
import type { ToastItem } from '@/layout/Toast'
import type { TaskRecord } from '@/types/harness'

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

export function useTasks({
  pushToast,
  onError,
}: {
  pushToast: (toast: ToastItem) => void
  onError: (error: unknown, fallback: string) => void
}) {
  const [tasks, setTasks] = useState<TaskRecord[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [includeArchived, setIncludeArchived] = useState(false)
  const [taskPrompt, setTaskPrompt] = useState('')
  const [creatingTask, setCreatingTask] = useState(false)

  const refreshTasks = useCallback(
    async (options?: { includeArchived?: boolean }) => {
      const data = await listTasks({ includeArchived: options?.includeArchived ?? includeArchived })
      setTasks(data.tasks)
      setSelectedTaskId((current) => {
        if (current && data.tasks.some((item) => item.id === current)) {
          return current
        }
        return data.tasks[0]?.id ?? null
      })
      return data.tasks
    },
    [includeArchived],
  )

  useEffect(() => {
    void refreshTasks()
  }, [refreshTasks])

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

  return {
    tasks,
    selectedTaskId,
    setSelectedTaskId,
    includeArchived,
    setIncludeArchived,
    taskPrompt,
    setTaskPrompt,
    creatingTask,
    refreshTasks,
    handleCreateTask,
  }
}
