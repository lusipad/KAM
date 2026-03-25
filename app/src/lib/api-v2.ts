import axios from 'axios';
import type {
  BootstrapThreadMessageResponse,
  CompareAgentSpec,
  ConversationRun,
  DecisionRecord,
  PostThreadMessageResponse,
  ProjectFileTreeRecord,
  ProjectLearningRecord,
  ProjectRecord,
  ProjectResourceRecord,
  ProjectThread,
  RunCompareResponse,
  ThreadRunArtifactRecord,
  UserPreferenceRecord,
} from '@/types/v2';

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

api.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(error),
);

const get = <T>(url: string, params?: unknown) => api.get<T, T>(url, params ? { params } : undefined);
const post = <TResponse, TBody = undefined>(url: string, data?: TBody) => api.post<TResponse, TResponse, TBody>(url, data);
const put = <TResponse, TBody>(url: string, data: TBody) => api.put<TResponse, TResponse, TBody>(url, data);
const del = <T>(url: string) => api.delete<T, T>(url);

export type ThreadMessageStreamEvent = {
  event: string;
  data: unknown;
};

function streamEventErrorMessage(data: unknown) {
  if (data && typeof data === 'object' && 'message' in data && typeof data.message === 'string') {
    return data.message;
  }
  return '';
}

async function streamJsonPost<TDone>(
  url: string,
  data: unknown,
  options?: {
    signal?: AbortSignal;
    onEvent?: (event: ThreadMessageStreamEvent) => void;
  },
): Promise<TDone | null> {
  const response = await fetch(`${API_BASE_URL}${url}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(data),
    signal: options?.signal,
  });

  if (!response.ok) {
    const message = await response.text().catch(() => '');
    throw new Error(message || `流式请求失败: ${response.status}`);
  }

  if (!response.body) {
    return null;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalPayload: TDone | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    let separatorIndex = buffer.indexOf('\n\n');
    while (separatorIndex >= 0) {
      const block = buffer.slice(0, separatorIndex);
      buffer = buffer.slice(separatorIndex + 2);
      separatorIndex = buffer.indexOf('\n\n');

      if (!block.trim()) {
        continue;
      }

      const lines = block.split('\n');
      let eventName = 'message';
      const dataLines: string[] = [];
      for (const line of lines) {
        if (line.startsWith('event:')) {
          eventName = line.slice(6).trim() || 'message';
          continue;
        }
        if (line.startsWith('data:')) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
      if (!dataLines.length) {
        continue;
      }

      const rawData = dataLines.join('\n');
      let parsed: unknown = rawData;
      try {
        parsed = JSON.parse(rawData);
      } catch {
        parsed = rawData;
      }

      options?.onEvent?.({
        event: eventName,
        data: parsed,
      });

      if (eventName === 'error') {
        throw new Error(streamEventErrorMessage(parsed) || '流式请求失败');
      }

      if (eventName === 'result') {
        finalPayload = parsed as TDone;
      }

      if (eventName === 'done') {
        finalPayload = parsed as TDone;
      }
    }
  }

  if (!buffer.trim()) {
    return finalPayload;
  }

  const lines = buffer.split('\n');
  let eventName = 'message';
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith('event:')) {
      eventName = line.slice(6).trim() || 'message';
      continue;
    }
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) {
    return finalPayload;
  }

  const rawData = dataLines.join('\n');
  let parsed: unknown = rawData;
  try {
    parsed = JSON.parse(rawData);
  } catch {
    parsed = rawData;
  }
  options?.onEvent?.({
    event: eventName,
    data: parsed,
  });
  if (eventName === 'error') {
    throw new Error(streamEventErrorMessage(parsed) || '流式请求失败');
  }
  if (eventName === 'result') {
    finalPayload = parsed as TDone;
  }
  if (eventName === 'done') {
    finalPayload = parsed as TDone;
  }
  return finalPayload;
}

export const v2ProjectsApi = {
  list: (params?: { status?: string }) => get<{ projects: ProjectRecord[] }>('/v2/projects', params),
  create: (data: Partial<ProjectRecord> & { title: string }) => post<ProjectRecord, typeof data>('/v2/projects', data),
  getById: (projectId: string) => get<ProjectRecord>(`/v2/projects/${projectId}`),
  update: (projectId: string, data: Partial<ProjectRecord>) => put<ProjectRecord, typeof data>(`/v2/projects/${projectId}`, data),
  archive: (projectId: string) => post<ProjectRecord>(`/v2/projects/${projectId}/archive`),
  listResources: (projectId: string, params?: { pinned?: boolean }) =>
    get<{ resources: ProjectResourceRecord[] }>(`/v2/projects/${projectId}/resources`, params),
  addResource: (projectId: string, data: Partial<ProjectResourceRecord> & { type: string; uri: string }) =>
    post<ProjectResourceRecord, typeof data>(`/v2/projects/${projectId}/resources`, data),
  deleteResource: (projectId: string, resourceId: string) => del<{ message: string }>(`/v2/projects/${projectId}/resources/${resourceId}`),
  listFiles: (projectId: string, params?: { path?: string; include_hidden?: boolean; query?: string; entry_type?: string }) =>
    get<ProjectFileTreeRecord>(`/v2/projects/${projectId}/files`, params),
};

export const v2ThreadsApi = {
  list: (projectId: string, params?: { status?: string }) =>
    get<{ threads: ProjectThread[] }>(`/v2/projects/${projectId}/threads`, params),
  create: (projectId: string, data: Partial<ProjectThread> & { title?: string }) =>
    post<ProjectThread, typeof data>(`/v2/projects/${projectId}/threads`, data),
  getById: (threadId: string) => get<ProjectThread>(`/v2/threads/${threadId}`),
  postMessage: (
    threadId: string,
    data: {
      content: string;
      metadata?: Record<string, unknown>;
      createRun?: boolean;
      agent?: string;
      command?: string;
      model?: string;
      reasoningEffort?: string;
    },
  ) => post<PostThreadMessageResponse, typeof data>(`/v2/threads/${threadId}/messages`, data),
  postMessageStream: (
    threadId: string,
    data: {
      content: string;
      metadata?: Record<string, unknown>;
      createRun?: boolean;
      agent?: string;
      command?: string;
      model?: string;
      reasoningEffort?: string;
    },
    options?: {
      signal?: AbortSignal;
      onEvent?: (event: ThreadMessageStreamEvent) => void;
    },
  ) => streamJsonPost<PostThreadMessageResponse>(`/v2/threads/${threadId}/messages`, data, options),
  bootstrapMessage: (data: {
    content: string;
    metadata?: Record<string, unknown>;
    createRun?: boolean;
    agent?: string;
    command?: string;
    model?: string;
    reasoningEffort?: string;
    projectTitle?: string;
    projectDescription?: string;
    projectStatus?: string;
    repoPath?: string;
    checkCommands?: string[];
    projectSettings?: Record<string, unknown>;
    threadTitle?: string;
  }) => post<BootstrapThreadMessageResponse, typeof data>('/v2/bootstrap/message', data),
};

export const v2RunsApi = {
  list: (threadId: string) => get<{ runs: ConversationRun[] }>(`/v2/threads/${threadId}/runs`),
  create: (
    threadId: string,
    data: {
      agent?: string;
      command?: string;
      prompt?: string;
      model?: string;
      reasoningEffort?: string;
      maxRounds?: number;
      autoStart?: boolean;
      metadata?: Record<string, unknown>;
    },
  ) => post<ConversationRun, typeof data>(`/v2/threads/${threadId}/runs`, data),
  compare: (
    threadId: string,
    data: {
      prompt: string;
      agents: CompareAgentSpec[];
      maxRounds?: number;
      autoStart?: boolean;
      metadata?: Record<string, unknown>;
    },
  ) => post<RunCompareResponse, typeof data>(`/v2/threads/${threadId}/compare`, data),
  getById: (runId: string) => get<ConversationRun>(`/v2/runs/${runId}`),
  start: (runId: string) => post<ConversationRun>(`/v2/runs/${runId}/start`),
  getArtifacts: (runId: string) => get<{ artifacts: ThreadRunArtifactRecord[] }>(`/v2/runs/${runId}/artifacts`),
  cancel: (runId: string) => post<ConversationRun>(`/v2/runs/${runId}/cancel`),
  retry: (runId: string) => post<ConversationRun>(`/v2/runs/${runId}/retry`),
  adopt: (runId: string) => post<ConversationRun>(`/v2/runs/${runId}/adopt`),
};

export const v2MemoryApi = {
  listPreferences: (params?: { category?: string }) =>
    get<{ preferences: UserPreferenceRecord[] }>('/v2/memory/preferences', params),
  createPreference: (data: { category: string; key: string; value: string; sourceThreadId?: string }) =>
    post<UserPreferenceRecord, typeof data>('/v2/memory/preferences', data),
  updatePreference: (preferenceId: string, data: { value: string; sourceThreadId?: string }) =>
    put<UserPreferenceRecord, typeof data>(`/v2/memory/preferences/${preferenceId}`, data),
  listDecisions: (params?: { project_id?: string }) => get<{ decisions: DecisionRecord[] }>('/v2/memory/decisions', params),
  createDecision: (data: {
    projectId?: string;
    question: string;
    decision: string;
    reasoning?: string;
    sourceThreadId?: string;
  }) => post<DecisionRecord, typeof data>('/v2/memory/decisions', data),
  updateDecision: (decisionId: string, data: { question: string; decision: string; reasoning?: string; sourceThreadId?: string }) =>
    put<DecisionRecord, typeof data>(`/v2/memory/decisions/${decisionId}`, data),
  listLearnings: (params?: { project_id?: string; query?: string }) =>
    get<{ learnings: ProjectLearningRecord[] }>('/v2/memory/learnings', params),
  createLearning: (data: {
    projectId: string;
    content: string;
    embedding?: number[];
    sourceThreadId?: string;
  }) => post<ProjectLearningRecord, typeof data>('/v2/memory/learnings', data),
  updateLearning: (learningId: string, data: { content: string; embedding?: number[]; sourceThreadId?: string }) =>
    put<ProjectLearningRecord, typeof data>(`/v2/memory/learnings/${learningId}`, data),
  search: (params?: { query?: string; project_id?: string }) =>
    get<{
      preferences: UserPreferenceRecord[];
      decisions: DecisionRecord[];
      learnings: ProjectLearningRecord[];
    }>('/v2/memory/search', params),
};

export function getV2RunEventsUrl(runId: string, tailChars = 20000) {
  return `${API_BASE_URL}/v2/runs/${runId}/events?tail_chars=${tailChars}`;
}

export function getV2ThreadEventsUrl(threadId: string) {
  return `${API_BASE_URL}/v2/threads/${threadId}/events`;
}
