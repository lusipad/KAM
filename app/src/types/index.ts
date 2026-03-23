// AI工作助手 - 类型定义

// ===== 知识管理模块 =====
export interface Note {
  id: string;
  title: string;
  content: string;
  contentType: 'markdown' | 'rich-text' | 'block';
  parentId?: string;
  path: string;
  version: number;
  metadata: {
    tags: string[];
    aliases: string[];
    extractedTags: string[];
    summary?: string;
    properties: Record<string, any>;
  };
  stats: {
    wordCount: number;
    linkCount: number;
    backlinkCount: number;
    viewCount: number;
    readingTime: number;
  };
  createdAt: Date;
  updatedAt: Date;
}

export interface Link {
  id: string;
  sourceNoteId: string;
  targetNoteId: string;
  type: 'wiki' | 'tag' | 'block' | 'embed' | 'external';
  context: {
    sourceText: string;
    targetText?: string;
    position: { start: number; end: number };
  };
  isResolved: boolean;
  isEmbed: boolean;
  createdAt: Date;
}

export interface Tag {
  id: string;
  name: string;
  displayName: string;
  color?: string;
  icon?: string;
  parentId?: string;
  path: string;
  description?: string;
  noteCount: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface GraphNode {
  id: string;
  title: string;
  type: 'note' | 'tag' | 'attachment';
  metadata: {
    createdAt: Date;
    updatedAt: Date;
    wordCount: number;
    tags: string[];
  };
  visual: {
    size: number;
    color: string;
    x?: number;
    y?: number;
  };
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
  strength: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ===== 长期记忆模块 =====
export type MemoryType = 'fact' | 'procedure' | 'episodic';
export type MemoryLayer = 'working' | 'short-term' | 'long-term';

export interface Memory {
  id: string;
  userId: string;
  memoryType: MemoryType;
  category: string;
  content: string;
  contentVector?: number[];
  summary?: string;
  summaryVector?: number[];
  metadata: {
    createdAt: Date;
    updatedAt: Date;
    lastAccessed: Date;
    accessCount: number;
    importanceScore: number;
    confidenceScore: number;
    source: string;
    tags: string[];
    relatedMemories: string[];
    expirationDate?: Date;
  };
  context: {
    sessionId?: string;
    taskId?: string;
    conversationId?: string;
    temporalContext?: string;
  };
}

export interface MemoryQuery {
  query: string;
  userId: string;
  context?: {
    recentMemories?: Memory[];
    currentTime?: Date;
    sessionId?: string;
  };
  topK?: number;
  filters?: {
    memoryType?: MemoryType[];
    category?: string[];
    dateRange?: { start: Date; end: Date };
  };
}

// ===== ClawTeam代理模块 =====
export type AgentRole = 'planner' | 'decomposer' | 'router' | 'executor' | 'specialist' | 'validator' | 'critic' | 'synthesizer';
export type TeamTopology = 'hierarchical' | 'peer-to-peer' | 'blackboard' | 'pipeline';

export interface Agent {
  id: string;
  name: string;
  role: AgentRole;
  description: string;
  capabilities: string[];
  systemPrompt: string;
  model: string;
  temperature: number;
  maxTokens: number;
  tools: string[];
  isActive: boolean;
  createdAt: Date;
}

export interface AgentTeam {
  id: string;
  name: string;
  description: string;
  topology: TeamTopology;
  agents: Agent[];
  coordinatorId?: string;
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

export interface Task {
  id: string;
  teamId: string;
  description: string;
  goal: string;
  constraints?: string[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  priority: number;
  subtasks: SubTask[];
  results: TaskResult[];
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
}

export interface SubTask {
  id: string;
  taskId: string;
  description: string;
  complexity: number;
  requiredCapabilities: string[];
  assignedAgentId?: string;
  dependencies: string[];
  status: 'pending' | 'running' | 'completed' | 'failed';
  expectedOutput?: string;
  actualOutput?: string;
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
}

export interface TaskResult {
  subtaskId: string;
  agentId: string;
  output: string;
  confidence: number;
  metadata: Record<string, any>;
  timestamp: Date;
}

export interface Tool {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  schema: {
    input: Record<string, any>;
    output: Record<string, any>;
  };
  execution: {
    mode: 'sync' | 'async';
    timeout: number;
    retryPolicy: {
      maxRetries: number;
      backoff: string;
    };
    idempotent: boolean;
  };
  permissions: {
    requiredScopes: string[];
    sensitiveData: boolean;
    auditRequired: boolean;
  };
  isActive: boolean;
  createdAt: Date;
  updatedAt: Date;
}

// ===== Azure DevOps集成模块 =====
export interface AzureDevOpsConfig {
  id: string;
  name: string;
  serverUrl: string;
  collection: string;
  project: string;
  authType: 'pat' | 'oauth' | 'ntlm';
  credentials: {
    pat?: string;
    username?: string;
    password?: string;
    accessToken?: string;
    refreshToken?: string;
    expiresAt?: Date;
  };
  scopes: string[];
  isActive: boolean;
  lastSyncAt?: Date;
  createdAt: Date;
  updatedAt: Date;
}

export interface WorkItem {
  id: number;
  rev: number;
  url: string;
  fields: Record<string, any>;
  relations?: any[];
  comments?: WorkItemComment[];
  createdAt: Date;
  updatedAt: Date;
}

export interface WorkItemComment {
  id: number;
  text: string;
  createdBy: string;
  createdAt: Date;
  updatedAt?: Date;
}

export interface GitRepository {
  id: string;
  name: string;
  url: string;
  project: string;
  defaultBranch: string;
  size: number;
  remoteUrl: string;
}

export interface GitCommit {
  commitId: string;
  comment: string;
  author: {
    name: string;
    email: string;
    date: Date;
  };
  committer: {
    name: string;
    email: string;
    date: Date;
  };
  parents: string[];
  url: string;
}

export interface Build {
  id: number;
  buildNumber: string;
  status: 'none' | 'inProgress' | 'completed' | 'cancelling' | 'postponed' | 'notStarted';
  result?: 'none' | 'succeeded' | 'partiallySucceeded' | 'failed' | 'canceled';
  queueTime: Date;
  startTime?: Date;
  finishTime?: Date;
  definition: {
    id: number;
    name: string;
  };
  requester: {
    displayName: string;
    uniqueName: string;
  };
}

export interface SyncState {
  entityType: string;
  project: string;
  lastSyncTime: Date;
  lastSyncId?: string;
  continuationToken?: string;
  syncCount: number;
}

// ===== AI对话模块 =====
export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: Date;
  metadata?: {
    model?: string;
    tokens?: number;
    latency?: number;
    intent?: string;
    entities?: Record<string, any>;
  };
}

export interface Conversation {
  id: string;
  title: string;
  messages: Message[];
  context?: {
    noteIds?: string[];
    memoryIds?: string[];
    taskId?: string;
    adoConfigId?: string;
  };
  createdAt: Date;
  updatedAt: Date;
}

// ===== 应用状态 =====
export interface AppState {
  // 当前视图
  currentView: 'knowledge' | 'memory' | 'clawteam' | 'azure-devops' | 'chat';
  
  // 侧边栏状态
  sidebarCollapsed: boolean;
  
  // 主题
  theme: 'light' | 'dark' | 'system';
  
  // 用户信息
  user?: {
    id: string;
    name: string;
    email: string;
    avatar?: string;
    preferences: Record<string, any>;
  };
}
