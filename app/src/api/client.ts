import type {
  HomeFeedPayload,
  MemoryItem,
  ProjectSummary,
  RunRecord,
  ThreadDetail,
  ThreadSummary,
  WatcherEventRecord,
  WatcherRecord,
  WatcherUpdatePayload,
} from '@/types/v3'

const API_BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `${response.status} ${response.statusText}`)
  }

  return response.json() as Promise<T>
}

export function listProjects() {
  return request<{ projects: ProjectSummary[] }>('/projects')
}

export function createProject(payload: { title: string; repoPath?: string | null }) {
  return request<ProjectSummary>('/projects', {
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
