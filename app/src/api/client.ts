import type {
  HomeFeedPayload,
  MemoryItem,
  ProjectSummary,
  ReviewCompareRecord,
  RunRecord,
  RunArtifactRecord,
  TaskDetail,
  TaskRecord,
  TaskRefRecord,
  ThreadDetail,
  ThreadSummary,
  WatcherEventRecord,
  WatcherRecord,
  WatcherUpdatePayload,
} from '@/types/v3'

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

export function listProjects() {
  return request<{ projects: ProjectSummary[] }>('/projects')
}

export function listTasks() {
  return request<{ tasks: TaskRecord[] }>('/tasks')
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

export function createTaskRun(taskId: string, payload: { agent: 'codex' | 'claude-code' | 'custom'; task: string }) {
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

export function createProject(payload: { title: string; repoPath?: string | null }) {
  return request<ProjectSummary>('/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function bootstrapConversation(payload: { prompt: string; repoPath?: string | null }) {
  return request<{ project: ProjectSummary; thread: ThreadSummary }>('/projects/bootstrap', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function createThread(projectId: string, payload: { title?: string; externalRef?: Record<string, unknown> | null }) {
  return request<ThreadSummary>(`/projects/${projectId}/threads`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function listThreads() {
  return request<{ threads: ThreadSummary[] }>('/threads')
}

export function getThread(threadId: string) {
  return request<ThreadDetail>(`/threads/${threadId}`)
}

export function getHomeFeed() {
  return request<HomeFeedPayload>('/home/feed')
}

export function getMemory(projectId?: string) {
  const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return request<{ memories: MemoryItem[] }>(`/memory${params}`)
}

export function listWatchers() {
  return request<{ watchers: WatcherRecord[] }>('/watchers')
}

export function getWatcher(watcherId: string) {
  return request<WatcherRecord>(`/watchers/${watcherId}`)
}

export function updateWatcher(watcherId: string, payload: WatcherUpdatePayload) {
  return request<WatcherRecord>(`/watchers/${watcherId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function getWatcherEvents(watcherId: string) {
  return request<{ events: WatcherEventRecord[] }>(`/watchers/${watcherId}/events`)
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

export function pauseWatcher(watcherId: string) {
  return request<WatcherRecord>(`/watchers/${watcherId}/pause`, {
    method: 'POST',
  })
}

export function activateWatcher(watcherId: string) {
  return request<WatcherRecord>(`/watchers/${watcherId}/activate`, {
    method: 'POST',
  })
}

export function resumeWatcher(watcherId: string) {
  return request<WatcherRecord>(`/watchers/${watcherId}/resume`, {
    method: 'POST',
  })
}

export function runWatcherNow(watcherId: string) {
  return request<{ event: WatcherEventRecord | null }>(`/watchers/${watcherId}/run-now`, {
    method: 'POST',
  })
}

export function executeWatcherAction(eventId: string, actionIndex: number) {
  return request<{ ok: boolean; runId?: string; error?: string }>(`/watchers/events/${eventId}/actions/${actionIndex}`, {
    method: 'POST',
  })
}

export function dismissWatcherEvent(eventId: string) {
  return request<WatcherEventRecord>(`/watchers/events/${eventId}/dismiss`, {
    method: 'POST',
  })
}

export async function createDraftMemory(payload: {
  projectId?: string | null
  category: MemoryItem['category']
  content: string
  rationale?: string | null
}) {
  return request<MemoryItem>('/memory', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
