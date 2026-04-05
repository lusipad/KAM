export type RunStatus = 'pending' | 'running' | 'passed' | 'failed' | 'cancelled'

export interface RunRecord {
  id: string
  taskId: string | null
  threadId: string | null
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

export interface RunArtifactRecord {
  id: string
  runId: string
  type: string
  content: string
  metadata: Record<string, unknown>
  createdAt: string
}

export interface TaskRefRecord {
  id: string
  taskId: string
  kind: string
  label: string
  value: string
  metadata: Record<string, unknown>
  createdAt: string
}

export interface ContextSnapshotRecord {
  id: string
  taskId: string
  summary: string
  content: string
  focus: string | null
  createdAt: string
}

export interface ReviewCompareRecord {
  id: string
  taskId: string
  title: string
  runIds: string[]
  summary: string | null
  createdAt: string
}

export interface TaskPlanSuggestion {
  title: string
  description: string
  priority: string
  labels: string[]
  metadata: Record<string, unknown>
  rationale: string
}

export interface TaskRecord {
  id: string
  title: string
  description: string | null
  repoPath: string | null
  status: string
  priority: string
  labels: string[]
  metadata: Record<string, unknown>
  archivedAt: string | null
  createdAt: string
  updatedAt: string
}

export interface TaskDetail extends TaskRecord {
  refs: TaskRefRecord[]
  snapshots: ContextSnapshotRecord[]
  runs: RunRecord[]
  reviews: ReviewCompareRecord[]
}

export interface TaskPlanResponse {
  taskId: string
  suggestions: TaskPlanSuggestion[]
  tasks: TaskRecord[]
}
