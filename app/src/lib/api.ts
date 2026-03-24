// API客户端 - 与后端通信
import axios from 'axios';

// API基础URL
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';

// 获取用户API配置
function getUserApiConfig() {
  if (typeof window === 'undefined') return null;
  return {
    openaiApiKey: localStorage.getItem('openai-api-key'),
    openaiBaseUrl: localStorage.getItem('openai-base-url'),
    azureApiKey: localStorage.getItem('azure-api-key'),
    azureEndpoint: localStorage.getItem('azure-endpoint'),
    defaultModel: localStorage.getItem('default-model'),
  };
}

// 创建axios实例
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 添加用户API配置到请求头
    const userConfig = getUserApiConfig();
    if (userConfig) {
      if (userConfig.openaiApiKey) {
        config.headers['X-OpenAI-Key'] = userConfig.openaiApiKey;
      }
      if (userConfig.openaiBaseUrl) {
        config.headers['X-OpenAI-URL'] = userConfig.openaiBaseUrl;
      }
      if (userConfig.azureApiKey) {
        config.headers['X-Azure-Key'] = userConfig.azureApiKey;
      }
      if (userConfig.azureEndpoint) {
        config.headers['X-Azure-Endpoint'] = userConfig.azureEndpoint;
      }
      if (userConfig.defaultModel) {
        config.headers['X-Default-Model'] = userConfig.defaultModel;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API错误:', error);
    return Promise.reject(error);
  }
);

// ========== 笔记API ==========
export const notesApi = {
  getAll: (params?: { search?: string; tag?: string; limit?: number; offset?: number }) =>
    api.get('/notes', { params }),
  
  create: (data: { title?: string; content?: string; content_type?: string; metadata?: any }) =>
    api.post('/notes', data),
  
  getById: (id: string) =>
    api.get(`/notes/${id}`),
  
  update: (id: string, data: { title?: string; content?: string; metadata?: any }) =>
    api.put(`/notes/${id}`, data),
  
  delete: (id: string) =>
    api.delete(`/notes/${id}`),
  
  getLinks: (id: string) =>
    api.get(`/notes/${id}/links`),
  
  getRelated: (id: string, limit?: number) =>
    api.get(`/notes/${id}/related`, { params: { limit } }),
};

// ========== 记忆API ==========
export const memoriesApi = {
  getAll: (params?: { memory_type?: string; category?: string; limit?: number; offset?: number }) =>
    api.get('/memories', { params }),
  
  create: (data: { content: string; memory_type?: string; category?: string; metadata?: any; context?: any }) =>
    api.post('/memories', data),
  
  search: (query: string, params?: { top_k?: number; memory_type?: string; min_importance?: number }) =>
    api.get('/memories/search', { params: { query, ...params } }),
  
  getById: (id: string) =>
    api.get(`/memories/${id}`),
  
  delete: (id: string) =>
    api.delete(`/memories/${id}`),
  
  extract: (text: string) =>
    api.post('/memories/extract', { text }),
};

// ========== ClawTeam API ==========
export const clawteamApi = {
  // 代理
  getAgents: () =>
    api.get('/clawteam/agents'),
  
  createAgent: (data: any) =>
    api.post('/clawteam/agents', data),
  
  getAgent: (id: string) =>
    api.get(`/clawteam/agents/${id}`),
  
  updateAgent: (id: string, data: any) =>
    api.put(`/clawteam/agents/${id}`, data),
  
  deleteAgent: (id: string) =>
    api.delete(`/clawteam/agents/${id}`),
  
  // 团队
  getTeams: () =>
    api.get('/clawteam/teams'),
  
  createTeam: (data: any) =>
    api.post('/clawteam/teams', data),
  
  getTeam: (id: string) =>
    api.get(`/clawteam/teams/${id}`),
  
  updateTeam: (id: string, data: any) =>
    api.put(`/clawteam/teams/${id}`, data),
  
  deleteTeam: (id: string) =>
    api.delete(`/clawteam/teams/${id}`),
  
  // 任务
  executeTask: (teamId: string, description: string) =>
    api.post(`/clawteam/teams/${teamId}/execute`, { description }),
  
  getTasks: (teamId?: string) =>
    api.get('/clawteam/tasks', { params: { team_id: teamId } }),
  
  getTask: (id: string) =>
    api.get(`/clawteam/tasks/${id}`),
};

// ========== Azure DevOps API ==========
export const adoApi = {
  // 配置
  getConfigs: () =>
    api.get('/ado/configs'),
  
  createConfig: (data: any) =>
    api.post('/ado/configs', data),
  
  getConfig: (id: string) =>
    api.get(`/ado/configs/${id}`),
  
  updateConfig: (id: string, data: any) =>
    api.put(`/ado/configs/${id}`, data),
  
  deleteConfig: (id: string) =>
    api.delete(`/ado/configs/${id}`),
  
  testConnection: (id: string) =>
    api.post(`/ado/configs/${id}/test`),
  
  // 数据
  getWorkItems: (configId: string, params?: { query?: string; top?: number }) =>
    api.get(`/ado/configs/${configId}/workitems`, { params }),
  
  getRepositories: (configId: string) =>
    api.get(`/ado/configs/${configId}/repositories`),
  
  getBuilds: (configId: string, params?: { top?: number }) =>
    api.get(`/ado/configs/${configId}/builds`, { params }),
};

// ========== 对话API ==========
export const conversationsApi = {
  getAll: () =>
    api.get('/conversations'),
  
  create: (data?: { title?: string; context?: any }) =>
    api.post('/conversations', data),
  
  getById: (id: string) =>
    api.get(`/conversations/${id}`),
  
  delete: (id: string) =>
    api.delete(`/conversations/${id}`),
  
  getMessages: (id: string) =>
    api.get(`/conversations/${id}/messages`),
  
  sendMessage: (id: string, content: string, useMemory?: boolean) =>
    api.post(`/conversations/${id}/messages`, { content, use_memory: useMemory }),
  
  clearMessages: (id: string) =>
    api.delete(`/conversations/${id}/messages`),
};

// ========== Lite 任务台 API ==========
export const tasksApi = {
  getAll: (params?: { status?: string }) =>
    api.get('/tasks', { params }),

  create: (data: {
    title: string;
    description?: string;
    status?: string;
    priority?: string;
    tags?: string[];
    metadata?: Record<string, any>;
  }) => api.post('/tasks', data),

  getById: (taskId: string) =>
    api.get(`/tasks/${taskId}`),

  update: (
    taskId: string,
    data: {
      title?: string;
      description?: string;
      status?: string;
      priority?: string;
      tags?: string[];
      metadata?: Record<string, any>;
    }
  ) => api.put(`/tasks/${taskId}`, data),

  archive: (taskId: string) =>
    api.post(`/tasks/${taskId}/archive`),

  addRef: (
    taskId: string,
    data:
      | {
          ref_type: string;
          ref: string;
          title?: string;
          metadata?: Record<string, any>;
        }
      | {
          type: string;
          label: string;
          value: string;
          metadata?: Record<string, any>;
        }
  ) => {
    const payload = 'ref_type' in data
      ? {
          type: data.ref_type,
          label: data.title || data.ref,
          value: data.ref,
          metadata: data.metadata,
        }
      : data;

    return api.post(`/tasks/${taskId}/refs`, payload);
  },

  resolveContext: (
    taskId: string,
    data?: {
      include_refs?: boolean;
      include_history?: boolean;
      include_memory?: boolean;
    }
  ) => api.post(`/tasks/${taskId}/context/resolve`, data || {}),

  getReview: (taskId: string) =>
    api.get(`/reviews/${taskId}`),

  compareReview: (taskId: string, data: { run_ids?: string[] } = {}) =>
    api.post(`/reviews/${taskId}/compare`, data),

  createRuns: (
    taskId: string,
    agents: Array<{
      name: string;
      type: string;
      command?: string;
    }>
  ) => api.post(`/tasks/${taskId}/runs`, { agents }),

  startRun: (runId: string) =>
    api.post(`/runs/${runId}/start`),

  cancelRun: (runId: string) =>
    api.post(`/runs/${runId}/cancel`),

  retryRun: (runId: string) =>
    api.post(`/runs/${runId}/retry`),

  applyPatch: (runId: string) =>
    api.post(`/runs/${runId}/apply-patch`),

  getRunArtifacts: (runId: string, params?: { tail_chars?: number }) =>
    api.get(`/runs/${runId}/artifacts`, { params }),
};

export const runsApi = {
  create: (
    taskId: string,
    data: {
      agent_type: string;
      agent_name?: string;
      instruction?: string;
      model?: string;
      command_template?: string;
      metadata?: Record<string, any>;
    }
  ) => api.post(`/tasks/${taskId}/runs`, data),

  list: (params?: { task_id?: string; status?: string }) =>
    api.get('/runs', { params }),

  getById: (runId: string) =>
    api.get(`/runs/${runId}`),

  start: (runId: string) =>
    api.post(`/runs/${runId}/start`),

  cancel: (runId: string) =>
    api.post(`/runs/${runId}/cancel`),

  retry: (runId: string) =>
    api.post(`/runs/${runId}/retry`),

  artifacts: (runId: string, params?: { tail_chars?: number }) =>
    api.get(`/runs/${runId}/artifacts`, { params }),
};

export const reviewsApi = {
  getByTaskId: (taskId: string) =>
    api.get(`/reviews/${taskId}`),

  compare: (
    taskId: string,
    data: { run_ids?: string[] }
  ) => api.post(`/reviews/${taskId}/compare`, data),
};

export default api;
