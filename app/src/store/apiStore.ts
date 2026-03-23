// API集成的状态管理
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { 
  notesApi, 
  memoriesApi, 
  clawteamApi, 
  adoApi, 
  conversationsApi 
} from '@/lib/api';
import type { 
  Note, Memory, Agent, AgentTeam, Task,
  AzureDevOpsConfig, WorkItem, GitRepository, Build,
  Conversation
} from '@/types';

// 知识管理状态
interface KnowledgeState {
  notes: Note[];
  currentNoteId?: string;
  isLoading: boolean;
  error: string | null;
}

interface KnowledgeActions {
  fetchNotes: () => Promise<void>;
  createNote: (data: Partial<Note>) => Promise<Note>;
  updateNote: (id: string, data: Partial<Note>) => Promise<void>;
  deleteNote: (id: string) => Promise<void>;
  setCurrentNote: (id?: string) => void;
}

// 记忆管理状态
interface MemoryState {
  memories: Memory[];
  searchResults: Memory[];
  isLoading: boolean;
  isSearching: boolean;
  error: string | null;
}

interface MemoryActions {
  fetchMemories: () => Promise<void>;
  searchMemories: (query: string) => Promise<void>;
  createMemory: (data: { content: string; memory_type?: string; category?: string; metadata?: any; context?: any }) => Promise<void>;
  deleteMemory: (id: string) => Promise<void>;
}

// ClawTeam状态
interface ClawTeamState {
  agents: Agent[];
  teams: AgentTeam[];
  tasks: Task[];
  isLoading: boolean;
  isExecuting: boolean;
  error: string | null;
}

interface ClawTeamActions {
  fetchAgents: () => Promise<void>;
  createAgent: (data: Partial<Agent>) => Promise<void>;
  deleteAgent: (id: string) => Promise<void>;
  fetchTeams: () => Promise<void>;
  createTeam: (data: Partial<AgentTeam>) => Promise<void>;
  deleteTeam: (id: string) => Promise<void>;
  executeTask: (teamId: string, description: string) => Promise<void>;
  fetchTasks: () => Promise<void>;
}

// Azure DevOps状态
interface AzureDevOpsState {
  configs: AzureDevOpsConfig[];
  currentConfigId?: string;
  workItems: WorkItem[];
  repositories: GitRepository[];
  builds: Build[];
  isLoading: boolean;
  isSyncing: boolean;
  error: string | null;
}

interface AzureDevOpsActions {
  fetchConfigs: () => Promise<void>;
  createConfig: (data: Partial<AzureDevOpsConfig>) => Promise<void>;
  deleteConfig: (id: string) => Promise<void>;
  setCurrentConfig: (id?: string) => void;
  fetchWorkItems: (configId: string) => Promise<void>;
  fetchRepositories: (configId: string) => Promise<void>;
  fetchBuilds: (configId: string) => Promise<void>;
}

// 对话状态
interface ChatState {
  conversations: Conversation[];
  currentConversationId?: string;
  isLoading: boolean;
  isGenerating: boolean;
  error: string | null;
}

interface ChatActions {
  fetchConversations: () => Promise<void>;
  createConversation: () => Promise<string>;
  deleteConversation: (id: string) => Promise<void>;
  setCurrentConversation: (id?: string) => void;
  sendMessage: (content: string) => Promise<void>;
}

// 全局状态
interface GlobalState {
  currentView: 'knowledge' | 'memory' | 'clawteam' | 'azure-devops' | 'chat';
  sidebarCollapsed: boolean;
  theme: 'light' | 'dark' | 'system';
  
  knowledge: KnowledgeState & KnowledgeActions;
  memory: MemoryState & MemoryActions;
  clawteam: ClawTeamState & ClawTeamActions;
  azureDevOps: AzureDevOpsState & AzureDevOpsActions;
  chat: ChatState & ChatActions;
  
  setCurrentView: (view: GlobalState['currentView']) => void;
  toggleSidebar: () => void;
  setTheme: (theme: GlobalState['theme']) => void;
}

export const useApiStore = create<GlobalState>()(
  persist(
    (set, get) => ({
      // 全局状态
      currentView: 'knowledge',
      sidebarCollapsed: false,
      theme: 'system',
      
      setCurrentView: (view) => set({ currentView: view }),
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setTheme: (theme) => set({ theme }),
      
      // ========== 知识管理 ==========
      knowledge: {
        notes: [],
        currentNoteId: undefined,
        isLoading: false,
        error: null,
        
        fetchNotes: async () => {
          set((state) => ({ knowledge: { ...state.knowledge, isLoading: true, error: null } }));
          try {
            const response: any = await notesApi.getAll();
            set((state) => ({ 
              knowledge: { ...state.knowledge, notes: response || [], isLoading: false } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              knowledge: { ...state.knowledge, error: error.message, isLoading: false } 
            }));
          }
        },
        
        createNote: async (data) => {
          try {
            const response: any = await notesApi.create(data);
            set((state) => ({ 
              knowledge: { 
                ...state.knowledge, 
                notes: [response, ...state.knowledge.notes],
                currentNoteId: response.id
              } 
            }));
            return response;
          } catch (error: any) {
            set((state) => ({ knowledge: { ...state.knowledge, error: error.message } }));
            throw error;
          }
        },
        
        updateNote: async (id, data) => {
          try {
            const response: any = await notesApi.update(id, data);
            set((state) => ({ 
              knowledge: { 
                ...state.knowledge, 
                notes: state.knowledge.notes.map(n => n.id === id ? response : n)
              } 
            }));
          } catch (error: any) {
            set((state) => ({ knowledge: { ...state.knowledge, error: error.message } }));
          }
        },
        
        deleteNote: async (id) => {
          try {
            await notesApi.delete(id);
            set((state) => ({ 
              knowledge: { 
                ...state.knowledge, 
                notes: state.knowledge.notes.filter(n => n.id !== id),
                currentNoteId: state.knowledge.currentNoteId === id 
                  ? undefined 
                  : state.knowledge.currentNoteId
              } 
            }));
          } catch (error: any) {
            set((state) => ({ knowledge: { ...state.knowledge, error: error.message } }));
          }
        },
        
        setCurrentNote: (id) => set((state) => ({ 
          knowledge: { ...state.knowledge, currentNoteId: id } 
        })),
      },
      
      // ========== 记忆管理 ==========
      memory: {
        memories: [],
        searchResults: [],
        isLoading: false,
        isSearching: false,
        error: null,
        
        fetchMemories: async () => {
          set((state) => ({ memory: { ...state.memory, isLoading: true, error: null } }));
          try {
            const response: any = await memoriesApi.getAll();
            set((state) => ({ 
              memory: { ...state.memory, memories: response || [], isLoading: false } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              memory: { ...state.memory, error: error.message, isLoading: false } 
            }));
          }
        },
        
        searchMemories: async (query) => {
          set((state) => ({ memory: { ...state.memory, isSearching: true, error: null } }));
          try {
            const response: any = await memoriesApi.search(query);
            set((state) => ({ 
              memory: { ...state.memory, searchResults: response || [], isSearching: false } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              memory: { ...state.memory, error: error.message, isSearching: false } 
            }));
          }
        },
        
        createMemory: async (data: { content: string; memory_type?: string; category?: string; metadata?: any; context?: any }) => {
          try {
            await memoriesApi.create(data);
            await get().memory.fetchMemories();
          } catch (error: any) {
            set((state) => ({ memory: { ...state.memory, error: error.message } }));
          }
        },
        
        deleteMemory: async (id) => {
          try {
            await memoriesApi.delete(id);
            set((state) => ({ 
              memory: { 
                ...state.memory, 
                memories: state.memory.memories.filter(m => m.id !== id) 
              } 
            }));
          } catch (error: any) {
            set((state) => ({ memory: { ...state.memory, error: error.message } }));
          }
        },
      },
      
      // ========== ClawTeam ==========
      clawteam: {
        agents: [],
        teams: [],
        tasks: [],
        isLoading: false,
        isExecuting: false,
        error: null,
        
        fetchAgents: async () => {
          set((state) => ({ clawteam: { ...state.clawteam, isLoading: true, error: null } }));
          try {
            const response: any = await clawteamApi.getAgents();
            set((state) => ({ 
              clawteam: { ...state.clawteam, agents: response.agents || [], isLoading: false } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              clawteam: { ...state.clawteam, error: error.message, isLoading: false } 
            }));
          }
        },
        
        createAgent: async (data) => {
          try {
            await clawteamApi.createAgent(data);
            await get().clawteam.fetchAgents();
          } catch (error: any) {
            set((state) => ({ clawteam: { ...state.clawteam, error: error.message } }));
          }
        },
        
        deleteAgent: async (id) => {
          try {
            await clawteamApi.deleteAgent(id);
            await get().clawteam.fetchAgents();
          } catch (error: any) {
            set((state) => ({ clawteam: { ...state.clawteam, error: error.message } }));
          }
        },
        
        fetchTeams: async () => {
          set((state) => ({ clawteam: { ...state.clawteam, isLoading: true, error: null } }));
          try {
            const response: any = await clawteamApi.getTeams();
            set((state) => ({ 
              clawteam: { ...state.clawteam, teams: response.teams || [], isLoading: false } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              clawteam: { ...state.clawteam, error: error.message, isLoading: false } 
            }));
          }
        },
        
        createTeam: async (data) => {
          try {
            await clawteamApi.createTeam(data);
            await get().clawteam.fetchTeams();
          } catch (error: any) {
            set((state) => ({ clawteam: { ...state.clawteam, error: error.message } }));
          }
        },
        
        deleteTeam: async (id) => {
          try {
            await clawteamApi.deleteTeam(id);
            await get().clawteam.fetchTeams();
          } catch (error: any) {
            set((state) => ({ clawteam: { ...state.clawteam, error: error.message } }));
          }
        },
        
        executeTask: async (teamId, description) => {
          set((state) => ({ clawteam: { ...state.clawteam, isExecuting: true, error: null } }));
          try {
            await clawteamApi.executeTask(teamId, description);
            await get().clawteam.fetchTasks();
            set((state) => ({ clawteam: { ...state.clawteam, isExecuting: false } }));
          } catch (error: any) {
            set((state) => ({ 
              clawteam: { ...state.clawteam, error: error.message, isExecuting: false } 
            }));
          }
        },
        
        fetchTasks: async () => {
          try {
            const response: any = await clawteamApi.getTasks();
            set((state) => ({ clawteam: { ...state.clawteam, tasks: response.tasks || [] } }));
          } catch (error: any) {
            set((state) => ({ clawteam: { ...state.clawteam, error: error.message } }));
          }
        },
      },
      
      // ========== Azure DevOps ==========
      azureDevOps: {
        configs: [],
        currentConfigId: undefined,
        workItems: [],
        repositories: [],
        builds: [],
        isLoading: false,
        isSyncing: false,
        error: null,
        
        fetchConfigs: async () => {
          set((state) => ({ azureDevOps: { ...state.azureDevOps, isLoading: true, error: null } }));
          try {
            const response: any = await adoApi.getConfigs();
            set((state) => ({ 
              azureDevOps: { 
                ...state.azureDevOps, 
                configs: response.configs || [], 
                isLoading: false 
              } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              azureDevOps: { ...state.azureDevOps, error: error.message, isLoading: false } 
            }));
          }
        },
        
        createConfig: async (data) => {
          try {
            await adoApi.createConfig(data);
            await get().azureDevOps.fetchConfigs();
          } catch (error: any) {
            set((state) => ({ azureDevOps: { ...state.azureDevOps, error: error.message } }));
          }
        },
        
        deleteConfig: async (id) => {
          try {
            await adoApi.deleteConfig(id);
            await get().azureDevOps.fetchConfigs();
          } catch (error: any) {
            set((state) => ({ azureDevOps: { ...state.azureDevOps, error: error.message } }));
          }
        },
        
        setCurrentConfig: (id) => set((state) => ({ 
          azureDevOps: { ...state.azureDevOps, currentConfigId: id } 
        })),
        
        fetchWorkItems: async (configId) => {
          set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: true, error: null } }));
          try {
            const response: any = await adoApi.getWorkItems(configId);
            set((state) => ({ 
              azureDevOps: { 
                ...state.azureDevOps, 
                workItems: response.workItems || [], 
                isSyncing: false 
              } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              azureDevOps: { ...state.azureDevOps, error: error.message, isSyncing: false } 
            }));
          }
        },
        
        fetchRepositories: async (configId) => {
          set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: true, error: null } }));
          try {
            const response: any = await adoApi.getRepositories(configId);
            set((state) => ({ 
              azureDevOps: { 
                ...state.azureDevOps, 
                repositories: response.repositories || [], 
                isSyncing: false 
              } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              azureDevOps: { ...state.azureDevOps, error: error.message, isSyncing: false } 
            }));
          }
        },
        
        fetchBuilds: async (configId) => {
          set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: true, error: null } }));
          try {
            const response: any = await adoApi.getBuilds(configId);
            set((state) => ({ 
              azureDevOps: { 
                ...state.azureDevOps, 
                builds: response.builds || [], 
                isSyncing: false 
              } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              azureDevOps: { ...state.azureDevOps, error: error.message, isSyncing: false } 
            }));
          }
        },
      },
      
      // ========== 对话 ==========
      chat: {
        conversations: [],
        currentConversationId: undefined,
        isLoading: false,
        isGenerating: false,
        error: null,
        
        fetchConversations: async () => {
          set((state) => ({ chat: { ...state.chat, isLoading: true, error: null } }));
          try {
            const response: any = await conversationsApi.getAll();
            set((state) => ({ 
              chat: { ...state.chat, conversations: response || [], isLoading: false } 
            }));
          } catch (error: any) {
            set((state) => ({ 
              chat: { ...state.chat, error: error.message, isLoading: false } 
            }));
          }
        },
        
        createConversation: async () => {
          try {
            const response: any = await conversationsApi.create();
            set((state) => ({ 
              chat: { 
                ...state.chat, 
                conversations: [response, ...state.chat.conversations],
                currentConversationId: response.id
              } 
            }));
            return response.id;
          } catch (error: any) {
            set((state) => ({ chat: { ...state.chat, error: error.message } }));
            throw error;
          }
        },
        
        deleteConversation: async (id) => {
          try {
            await conversationsApi.delete(id);
            set((state) => ({ 
              chat: { 
                ...state.chat, 
                conversations: state.chat.conversations.filter(c => c.id !== id),
                currentConversationId: state.chat.currentConversationId === id 
                  ? undefined 
                  : state.chat.currentConversationId
              } 
            }));
          } catch (error: any) {
            set((state) => ({ chat: { ...state.chat, error: error.message } }));
          }
        },
        
        setCurrentConversation: (id) => set((state) => ({ 
          chat: { ...state.chat, currentConversationId: id } 
        })),
        
        sendMessage: async (content) => {
          const conversationId = get().chat.currentConversationId;
          if (!conversationId) {
            // 创建新对话
            const newId = await get().chat.createConversation();
            if (!newId) return;
          }
          
          set((state) => ({ chat: { ...state.chat, isGenerating: true, error: null } }));
          
          try {
            await conversationsApi.sendMessage(
              get().chat.currentConversationId!, 
              content
            );
            
            // 更新对话列表
            await get().chat.fetchConversations();
            
            set((state) => ({ chat: { ...state.chat, isGenerating: false } }));
          } catch (error: any) {
            set((state) => ({ 
              chat: { ...state.chat, error: error.message, isGenerating: false } 
            }));
          }
        },
      },
    }),
    {
      name: 'ai-work-assistant-storage',
      partialize: (state) => ({
        currentView: state.currentView,
        sidebarCollapsed: state.sidebarCollapsed,
        theme: state.theme,
      }),
    }
  )
);
