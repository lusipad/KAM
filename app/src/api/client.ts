import type {
  IssueMonitorListResponse,
  IssueMonitorRecord,
  IssueMonitorRunSummary,
  OperatorActionResponse,
  OperatorControlPlaneResponse,
  ReviewCompareRecord,
  RunArtifactRecord,
  RunRecord,
  TaskDetail,
  TaskPlanResponse,
  TaskRecord,
  TaskRefRecord,
} from '@/types/harness'

const API_BASE = '/api'

export async function extractErrorMessage(response: Response) {
  const text = await response.text()
  if (!text) {
    return `${response.status} ${response.statusText}`.trim()
  }

  try {
    const payload = JSON.parse(text) as { detail?: unknown; message?: unknown }
    if (typeof payload.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim()
    }
    if (typeof payload.message === 'string' && payload.message.trim()) {
      return payload.message.trim()
    }
  } catch {
    // Ignore non-JSON responses and fall back to raw text.
  }

  return text
}

export function getErrorMessage(error: unknown, fallback = '操作失败，请稍后重试。') {
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim()
  }
  return fallback
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    throw new Error(await extractErrorMessage(response))
  }

  return response.json() as Promise<T>
}

export function listTasks(options?: { includeArchived?: boolean }) {
  const search = new URLSearchParams()
  if (options?.includeArchived) {
    search.set('include_archived', 'true')
  }
  const suffix = search.size ? `?${search.toString()}` : ''
  return request<{ tasks: TaskRecord[] }>(`/tasks${suffix}`)
}

export function getTask(taskId: string) {
  return request<TaskDetail>(`/tasks/${taskId}`)
}

export function createTask(payload: {
  title: string
  description?: string | null
  repoPath?: string | null
  status?: string
  priority?: string
  labels?: string[]
}) {
  return request<TaskRecord>('/tasks', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateTask(
  taskId: string,
  payload: {
    title?: string
    description?: string | null
    repoPath?: string | null
    status?: string
    priority?: string
    labels?: string[]
  },
) {
  return request<TaskRecord>(`/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function archiveTask(taskId: string) {
  return request<TaskRecord>(`/tasks/${taskId}/archive`, {
    method: 'POST',
  })
}

export function addTaskDependency(taskId: string, payload: { dependsOnTaskId: string }) {
  return request<TaskRecord>(`/tasks/${taskId}/dependencies`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteTaskDependency(taskId: string, dependsOnTaskId: string) {
  return request<TaskRecord>(`/tasks/${taskId}/dependencies/${dependsOnTaskId}`, {
    method: 'DELETE',
  })
}

export function addTaskRef(taskId: string, payload: { kind: string; label: string; value: string; metadata?: Record<string, unknown> | null }) {
  return request<TaskRefRecord>(`/tasks/${taskId}/refs`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function deleteTaskRef(taskId: string, refId: string) {
  return request<{ ok: boolean }>(`/tasks/${taskId}/refs/${refId}`, {
    method: 'DELETE',
  })
}

export function resolveTaskContext(taskId: string, payload: { focus?: string | null }) {
  return request<{ id: string; taskId: string; summary: string; content: string; focus: string | null; createdAt: string }>(
    `/tasks/${taskId}/context/resolve`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  )
}

export function createTaskRun(taskId: string, payload: { agent: 'codex' | 'claude-code'; task: string }) {
  return request<RunRecord>(`/tasks/${taskId}/runs`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getRunArtifacts(runId: string) {
  return request<{ artifacts: RunArtifactRecord[] }>(`/runs/${runId}/artifacts`)
}

export function createTaskCompare(taskId: string, payload: { runIds: string[]; title?: string | null }) {
  return request<ReviewCompareRecord>(`/reviews/${taskId}/compare`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function planTaskFollowUps(taskId: string, payload?: { createTasks?: boolean; limit?: number }) {
  return request<TaskPlanResponse>(`/tasks/${taskId}/plan`, {
    method: 'POST',
    body: JSON.stringify(payload ?? {}),
  })
}

export function getOperatorControlPlane(taskId?: string | null) {
  const search = new URLSearchParams()
  if (taskId) {
    search.set('task_id', taskId)
  }
  const suffix = search.size ? `?${search.toString()}` : ''
  return request<OperatorControlPlaneResponse>(`/operator/control-plane${suffix}`)
}

export function listIssueMonitors() {
  return request<IssueMonitorListResponse>('/issue-monitors')
}

export function upsertIssueMonitor(payload: {
  repo: string
  repoPath?: string | null
  runNow?: boolean
}) {
  return request<IssueMonitorRecord>('/issue-monitors', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function runIssueMonitorOnce(repo: string) {
  const [owner, name] = repo.split('/', 2)
  return request<IssueMonitorRunSummary>(`/issue-monitors/${encodeURIComponent(owner)}/${encodeURIComponent(name)}/run-once`, {
    method: 'POST',
  })
}

export function deleteIssueMonitorRecord(repo: string) {
  const [owner, name] = repo.split('/', 2)
  return request<{ ok: boolean; repo: string }>(`/issue-monitors/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

export function performOperatorAction(payload: {
  action: string
  taskId?: string | null
  runId?: string | null
}) {
  return request<OperatorActionResponse>('/operator/actions', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function adoptRun(runId: string) {
  return request<{ ok: boolean; adoptedAt?: string; error?: string }>(`/runs/${runId}/adopt`, {
    method: 'POST',
  })
}

export function retryRun(runId: string) {
  return request<RunRecord>(`/runs/${runId}/retry`, {
    method: 'POST',
  })
}

export function cancelRun(runId: string) {
  return request<RunRecord>(`/runs/${runId}/cancel`, {
    method: 'POST',
  })
}
