export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];

export interface JsonObject {
  [key: string]: JsonValue;
}

export interface WorkspaceTaskRef {
  id: string;
  taskId: string;
  type: string;
  label: string;
  value: string;
  metadata: JsonObject;
  createdAt: Date | string;
}

export interface ContextSnapshot {
  id: string;
  taskId: string;
  summary: string;
  data?: JsonObject;
  createdAt: Date | string;
}

export interface AgentRunArtifact {
  id: string;
  runId: string;
  type: string;
  title: string;
  content: string;
  path?: string;
  metadata: JsonObject;
  createdAt: Date | string;
}

export interface AgentRunRecord {
  id: string;
  taskId: string;
  agentName: string;
  agentType: string;
  status: 'planned' | 'queued' | 'running' | 'completed' | 'failed' | 'canceled';
  workdir?: string;
  prompt: string;
  command?: string;
  errorMessage?: string;
  metadata: JsonObject;
  artifacts?: AgentRunArtifact[];
  createdAt: Date | string;
  startedAt?: Date | string;
  completedAt?: Date | string;
}

export interface WorkspaceTask {
  id: string;
  title: string;
  description: string;
  status: 'inbox' | 'ready' | 'running' | 'review' | 'done' | 'archived';
  priority: 'low' | 'medium' | 'high';
  tags: string[];
  metadata: JsonObject;
  refs?: WorkspaceTaskRef[];
  runs?: AgentRunRecord[];
  latestSnapshot?: ContextSnapshot | null;
  createdAt: Date | string;
  updatedAt: Date | string;
}

export interface ReviewArtifactSummary {
  id: string;
  title: string;
  type: string;
}

export interface ReviewData {
  summary: string;
  runs: AgentRunRecord[];
  artifacts: ReviewArtifactSummary[];
}

export interface ComparisonRow {
  runId: string;
  agentName: string;
  status: string;
  artifactCount: number;
  changedFiles: number;
  untrackedFiles: number;
  hasPatch: boolean;
  repoRoot?: string;
}

export interface RunArtifactView {
  id: string;
  title: string;
  type: string;
  content: string;
  path?: string;
  truncated?: boolean;
  size?: number;
}

export interface TaskListResponse {
  tasks: WorkspaceTask[];
}

export interface ReviewCompareResponse {
  comparison: ComparisonRow[];
}

export interface RunArtifactListResponse {
  artifacts: RunArtifactView[];
}

export interface TaskCreateInput {
  title: string;
  description?: string;
  status?: WorkspaceTask['status'];
  priority?: WorkspaceTask['priority'];
  tags?: string[];
  metadata?: JsonObject;
}

export interface TaskUpdateInput {
  title?: string;
  description?: string;
  status?: WorkspaceTask['status'];
  priority?: WorkspaceTask['priority'];
  tags?: string[];
  metadata?: JsonObject;
}

export interface TaskRefCreateInput {
  type: string;
  label: string;
  value: string;
  metadata?: JsonObject;
}

export interface LegacyTaskRefInput {
  ref_type: string;
  ref: string;
  title?: string;
  metadata?: JsonObject;
}

export interface RunCreateInput {
  name: string;
  type: string;
  command?: string;
}
