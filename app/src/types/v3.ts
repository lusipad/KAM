export type RunStatus = 'pending' | 'running' | 'passed' | 'failed' | 'cancelled'

export interface ProjectSummary {
  id: string
  title: string
  repoPath: string | null
  createdAt: string
}

export interface ThreadSummary {
  id: string
  projectId: string
  title: string
  externalRef: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
  project: ProjectSummary | null
  hasActiveRun: boolean
  latestRunStatus: RunStatus | null
  latestRunSummary: string | null
}

export interface MessageRecord {
  id: string
  threadId: string
  role: 'user' | 'assistant' | 'system'
  content: string
  metadata: Record<string, unknown>
  createdAt: string
}

export interface RunRecord {
  id: string
  threadId: string
  agent: string
  status: RunStatus
  task: string
  resultSummary: string | null
  changedFiles: string[]
  checkPassed: boolean | null
  durationMs: number | null
  worktreePath: string | null
  adoptedAt: string | null
  rawOutput: string
  createdAt: string
}

export interface ThreadDetail extends ThreadSummary {
  messages: MessageRecord[]
  runs: RunRecord[]
}

export interface MemoryItem {
  id: string
  projectId: string | null
  scope: string
  category: 'preference' | 'decision' | 'fact' | 'learning'
  content: string
  rationale: string | null
  relevanceScore: number
  supersededBy: string | null
  sourceThreadId: string | null
  sourceMessageId: string | null
  createdAt: string
  lastAccessedAt: string
}

export interface WatcherRecord {
  id: string
  projectId: string
  name: string
  sourceType: string
  config: Record<string, unknown>
  scheduleType: string
  scheduleValue: string
  status: 'active' | 'paused' | 'draft'
  autoActionLevel: number
  lastRunAt: string | null
  lastState: Record<string, unknown>
  createdAt: string
}

export interface WatcherUpdatePayload {
  name?: string
  scheduleType?: string
  scheduleValue?: string
  autoActionLevel?: number
}

export interface WatcherEventRecord {
  id: string
  watcherId: string
  threadId: string | null
  eventType: string
  title: string
  summary: string
  rawData: Record<string, unknown>
  actions: Array<{ label: string; kind: string; params?: Record<string, unknown> }>
  status: 'pending' | 'handled' | 'dismissed'
  createdAt: string
  watcher: WatcherRecord | null
}

export type FeedItem =
  | ({ kind: 'run' } & RunRecord)
  | ({ kind: 'watcher_event' } & WatcherEventRecord)

export interface HomeFeedPayload {
  greeting: string
  summary: string
  needsAttention: FeedItem[]
  running: FeedItem[]
  recent: FeedItem[]
}
