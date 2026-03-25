import axios from 'axios';
import type {
  AgentRunRecord,
  AutonomyMetrics,
  AutonomySession,
  AutonomySessionCreateInput,
  AutonomySessionListResponse,
  LegacyTaskRefInput,
  ReviewCompareResponse,
  ReviewData,
  RunArtifactListResponse,
  RunCreateInput,
  TaskCreateInput,
  TaskListResponse,
  TaskRefCreateInput,
  TaskUpdateInput,
  WorkspaceTask,
} from '@/types';

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
  (error) => {
    console.error('API错误:', error);
    return Promise.reject(error);
  }
);

const get = <T>(url: string, params?: unknown) => api.get<T, T>(url, params ? { params } : undefined);
const post = <TResponse, TBody = undefined>(url: string, data?: TBody) => api.post<TResponse, TResponse, TBody>(url, data);
const put = <TResponse, TBody>(url: string, data: TBody) => api.put<TResponse, TResponse, TBody>(url, data);
const del = <T>(url: string) => api.delete<T, T>(url);

export const tasksApi = {
  getAll: (params?: { status?: string }) => get<TaskListResponse>('/tasks', params),

  create: (data: TaskCreateInput) => post<WorkspaceTask, TaskCreateInput>('/tasks', data),

  getById: (taskId: string) => get<WorkspaceTask>(`/tasks/${taskId}`),

  update: (taskId: string, data: TaskUpdateInput) => put<WorkspaceTask, TaskUpdateInput>(`/tasks/${taskId}`, data),

  archive: (taskId: string) => post<WorkspaceTask>(`/tasks/${taskId}/archive`),

  addRef: (taskId: string, data: LegacyTaskRefInput | TaskRefCreateInput) => {
    const payload =
      'ref_type' in data
        ? {
            type: data.ref_type,
            label: data.title || data.ref,
            value: data.ref,
            metadata: data.metadata,
          }
        : data;

    return post(`/tasks/${taskId}/refs`, payload);
  },

  deleteRef: (taskId: string, refId: string) => del<{ message: string }>(`/tasks/${taskId}/refs/${refId}`),

  resolveContext: (taskId: string) => post(`/tasks/${taskId}/context/resolve`),

  getReview: (taskId: string) => get<ReviewData>(`/reviews/${taskId}`),

  compareReview: (taskId: string, data: { run_ids?: string[] } = {}) =>
    post<ReviewCompareResponse, { run_ids?: string[] }>(`/reviews/${taskId}/compare`, data),

  createRuns: (taskId: string, agents: RunCreateInput[]) =>
    post<{ runs: AgentRunRecord[] }, { agents: RunCreateInput[] }>(`/tasks/${taskId}/runs`, { agents }),

  startRun: (runId: string) => post(`/runs/${runId}/start`),
  cancelRun: (runId: string) => post(`/runs/${runId}/cancel`),
  retryRun: (runId: string) => post(`/runs/${runId}/retry`),
  getRunArtifacts: (runId: string, params?: { tail_chars?: number }) => get<RunArtifactListResponse>(`/runs/${runId}/artifacts`, params),
};

export const runsApi = {
  list: (params?: { task_id?: string; status?: string }) => get<{ runs: AgentRunRecord[] }>('/runs', params),
  getById: (runId: string) => get<AgentRunRecord>(`/runs/${runId}`),
  start: (runId: string) => post(`/runs/${runId}/start`),
  cancel: (runId: string) => post(`/runs/${runId}/cancel`),
  retry: (runId: string) => post(`/runs/${runId}/retry`),
  artifacts: (runId: string, params?: { tail_chars?: number }) => get<RunArtifactListResponse>(`/runs/${runId}/artifacts`, params),
};

export const reviewsApi = {
  getByTaskId: (taskId: string) => get<ReviewData>(`/reviews/${taskId}`),
  compare: (taskId: string, data: { run_ids?: string[] }) =>
    post<ReviewCompareResponse, { run_ids?: string[] }>(`/reviews/${taskId}/compare`, data),
};

export const autonomyApi = {
  listTaskSessions: (taskId: string) => get<AutonomySessionListResponse>(`/tasks/${taskId}/autonomy/sessions`),
  createTaskSession: (taskId: string, data: AutonomySessionCreateInput) =>
    post<AutonomySession, AutonomySessionCreateInput>(`/tasks/${taskId}/autonomy/sessions`, data),
  createDogfoodSession: (taskId: string) => post<AutonomySession>(`/tasks/${taskId}/autonomy/dogfood`),
  getTaskMetrics: (taskId: string) => get<AutonomyMetrics>(`/tasks/${taskId}/autonomy/metrics`),
  getSession: (sessionId: string) => get<AutonomySession>(`/autonomy/sessions/${sessionId}`),
  startSession: (sessionId: string) => post<AutonomySession>(`/autonomy/sessions/${sessionId}/start`),
  interruptSession: (sessionId: string) => post<AutonomySession>(`/autonomy/sessions/${sessionId}/interrupt`),
  getMetrics: () => get<AutonomyMetrics>('/autonomy/metrics'),
};

export default api;
