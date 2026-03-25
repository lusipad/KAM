export interface ProjectResourceRecord {
  id: string;
  projectId: string;
  type: string;
  title?: string | null;
  uri: string;
  pinned: boolean;
  metadata: Record<string, unknown>;
  createdAt: Date | string;
}

export interface ProjectRecord {
  id: string;
  title: string;
  status: 'active' | 'paused' | 'done' | string;
  repoPath?: string | null;
  description: string;
  checkCommands: string[];
  settings: Record<string, unknown>;
  resourceCount: number;
  threadCount: number;
  resources?: ProjectResourceRecord[];
  pinnedResources?: ProjectResourceRecord[];
  threads?: ProjectThread[];
  createdAt: Date | string;
  updatedAt: Date | string;
}

export interface ProjectThread {
  id: string;
  projectId: string;
  title: string;
  status: 'active' | 'completed' | 'failed' | 'paused' | string;
  messageCount: number;
  latestRun?: ConversationRun | null;
  messages?: ThreadMessageRecord[];
  runs?: ConversationRun[];
  createdAt: Date | string;
  updatedAt: Date | string;
}

export interface ThreadRunArtifactRecord {
  id: string;
  runId: string;
  type: string;
  title: string;
  content: string;
  path?: string | null;
  round: number;
  metadata: Record<string, unknown>;
  truncated?: boolean;
  createdAt: Date | string;
}

export interface ConversationRun {
  id: string;
  threadId: string;
  messageId?: string | null;
  agent: string;
  model?: string | null;
  reasoningEffort?: string | null;
  command?: string | null;
  status: 'pending' | 'running' | 'checking' | 'passed' | 'failed' | 'cancelled' | string;
  workDir?: string | null;
  round: number;
  maxRounds: number;
  durationMs?: number | null;
  error?: string | null;
  metadata: Record<string, unknown>;
  artifacts?: ThreadRunArtifactRecord[];
  createdAt: Date | string;
  completedAt?: Date | string | null;
}

export interface ThreadMessageRecord {
  id: string;
  threadId: string;
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
  metadata: Record<string, unknown>;
  runs?: ConversationRun[];
  createdAt: Date | string;
}

export interface UserPreferenceRecord {
  id: string;
  category: string;
  key: string;
  value: string;
  sourceThreadId?: string | null;
  createdAt: Date | string;
}

export interface DecisionRecord {
  id: string;
  projectId?: string | null;
  question: string;
  decision: string;
  reasoning: string;
  sourceThreadId?: string | null;
  createdAt: Date | string;
}

export interface ProjectLearningRecord {
  id: string;
  projectId: string;
  content: string;
  embedding?: number[] | null;
  sourceThreadId?: string | null;
  createdAt: Date | string;
}

export interface ProjectFileEntryRecord {
  name: string;
  path: string;
  type: 'dir' | 'file' | string;
  size?: number | null;
}

export interface ProjectFileTreeRecord {
  rootPath: string;
  currentPath: string;
  parentPath?: string | null;
  entries: ProjectFileEntryRecord[];
  totalEntries?: number;
  filteredEntries?: number;
  query?: string;
  entryType?: 'dir' | 'file' | string | null;
  includeHidden?: boolean;
}

export interface CompareAgentSpec {
  agent: string;
  label?: string | null;
  command?: string | null;
  model?: string | null;
  reasoningEffort?: string | null;
  metadata?: Record<string, unknown>;
}

export interface RunCompareResponse {
  compareId: string;
  threadId: string;
  prompt: string;
  requestedAgents: CompareAgentSpec[];
  message?: ThreadMessageRecord | null;
  runs: ConversationRun[];
}

export interface PostThreadMessageResponse {
  message: ThreadMessageRecord;
  reply?: ThreadMessageRecord | null;
  runs: ConversationRun[];
  preferences?: UserPreferenceRecord[];
  routerMode?: string;
  compareId?: string | null;
}

export interface BootstrapThreadMessageResponse extends PostThreadMessageResponse {
  project: ProjectRecord;
  thread: ProjectThread;
}
