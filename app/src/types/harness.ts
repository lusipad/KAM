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

export interface SuggestedTaskRefRecord {
  kind: string
  label: string
  value: string
  metadata: Record<string, unknown>
}

export interface TaskPlanSuggestion {
  title: string
  description: string
  priority: string
  labels: string[]
  metadata: Record<string, unknown>
  rationale: string
  recommendedPrompt: string
  recommendedAgent: string
  acceptanceChecks: string[]
  suggestedRefs: SuggestedTaskRefRecord[]
}

export interface TaskDependencyRecord {
  taskId: string
  title: string
  status: string
  resolved: boolean
  missing: boolean
}

export interface TaskDependencyState {
  dependsOnTaskIds: string[]
  dependencies: TaskDependencyRecord[]
  blockingTaskIds: string[]
  blockedBy: TaskDependencyRecord[]
  ready: boolean
  summary: string | null
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
  dependencyState?: TaskDependencyState
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

export interface TaskDispatchResponse {
  task: TaskRecord
  run: RunRecord
  source: string
  plannedFromTaskId: string | null
}

export interface TaskContinueResponse {
  action: 'adopt' | 'retry' | 'plan_and_dispatch' | 'stop'
  reason: string
  summary: string
  task: TaskRecord | null
  run: RunRecord | null
  source: string | null
  plannedFromTaskId: string | null
  adoptedAt: string | null
  scopeTaskId: string | null
  error: string | null
}

export interface TaskAutoDriveResponse {
  task: TaskRecord
  scopeTaskId: string
  enabled: boolean
  running: boolean
  summary: string
}

export interface AutoDriveEventRecord {
  recordedAt: string
  status: string | null
  action: string | null
  reason: string | null
  summary: string | null
  error: string | null
  taskId: string | null
  scopeTaskId: string | null
  runId: string | null
  runTaskId: string | null
}

export interface GlobalAutoDriveLeaseStatus {
  ownerId: string | null
  pid: number | null
  hostname: string | null
  acquiredAt: string | null
  heartbeatAt: string | null
  ownedByCurrentProcess: boolean
  stale: boolean
}

export interface GlobalAutoDriveResponse {
  enabled: boolean
  running: boolean
  status: string
  summary: string
  lastAction: string | null
  lastReason: string | null
  currentTaskId: string | null
  currentScopeTaskId: string | null
  currentRunId: string | null
  loopCount: number
  error: string | null
  updatedAt: string | null
  lease: GlobalAutoDriveLeaseStatus | null
  recentEvents: AutoDriveEventRecord[]
}
