import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { 
  Note, Link, Tag, 
  Memory, 
  Agent, AgentTeam, Task, Tool,
  AzureDevOpsConfig, WorkItem, GitRepository, Build,
  Message, Conversation,
  AppState 
} from '@/types';

// ===== 全局状态 =====
interface GlobalState extends AppState {
  // 子状态
  knowledge: {
    notes: Note[];
    links: Link[];
    tags: Tag[];
    currentNoteId?: string;
    searchQuery: string;
    viewMode: 'list' | 'graph' | 'tree';
  };
  memory: {
    memories: Memory[];
    currentQuery: string;
    searchResults: Memory[];
    isSearching: boolean;
  };
  clawteam: {
    agents: Agent[];
    teams: AgentTeam[];
    tasks: Task[];
    tools: Tool[];
    currentTeamId?: string;
    currentTaskId?: string;
    isExecuting: boolean;
  };
  azureDevOps: {
    configs: AzureDevOpsConfig[];
    currentConfigId?: string;
    workItems: WorkItem[];
    repositories: GitRepository[];
    builds: Build[];
    isSyncing: boolean;
    syncStates: Record<string, any>;
  };
  chat: {
    conversations: Conversation[];
    currentConversationId?: string;
    isGenerating: boolean;
    inputMessage: string;
  };
  
  // 全局操作
  setCurrentView: (view: AppState['currentView']) => void;
  toggleSidebar: () => void;
  setTheme: (theme: AppState['theme']) => void;
  setUser: (user?: AppState['user']) => void;
  
  // 知识管理操作
  setNotes: (notes: Note[]) => void;
  addNote: (note: Note) => void;
  updateNote: (id: string, updates: Partial<Note>) => void;
  deleteNote: (id: string) => void;
  setCurrentNote: (id?: string) => void;
  setSearchQuery: (query: string) => void;
  setViewMode: (mode: 'list' | 'graph' | 'tree') => void;
  getNoteById: (id: string) => Note | undefined;
  getLinkedNotes: (noteId: string) => Note[];
  getNotesByTag: (tagName: string) => Note[];
  
  // 记忆管理操作
  setMemories: (memories: Memory[]) => void;
  addMemory: (memory: Memory) => void;
  updateMemory: (id: string, updates: Partial<Memory>) => void;
  deleteMemory: (id: string) => void;
  setCurrentQuery: (query: string) => void;
  setSearchResults: (results: Memory[]) => void;
  setIsSearching: (isSearching: boolean) => void;
  searchMemories: (query: string) => Promise<Memory[]>;
  
  // ClawTeam操作
  setAgents: (agents: Agent[]) => void;
  addAgent: (agent: Agent) => void;
  updateAgent: (id: string, updates: Partial<Agent>) => void;
  deleteAgent: (id: string) => void;
  setTeams: (teams: AgentTeam[]) => void;
  addTeam: (team: AgentTeam) => void;
  updateTeam: (id: string, updates: Partial<AgentTeam>) => void;
  deleteTeam: (id: string) => void;
  setCurrentTeam: (id?: string) => void;
  setTasks: (tasks: Task[]) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  setCurrentTask: (id?: string) => void;
  setTools: (tools: Tool[]) => void;
  setIsExecuting: (isExecuting: boolean) => void;
  executeTask: (teamId: string, description: string) => Promise<void>;
  
  // Azure DevOps操作
  setConfigs: (configs: AzureDevOpsConfig[]) => void;
  addConfig: (config: AzureDevOpsConfig) => void;
  updateConfig: (id: string, updates: Partial<AzureDevOpsConfig>) => void;
  deleteConfig: (id: string) => void;
  setCurrentConfig: (id?: string) => void;
  setWorkItems: (workItems: WorkItem[]) => void;
  addWorkItems: (workItems: WorkItem[]) => void;
  setRepositories: (repositories: GitRepository[]) => void;
  setBuilds: (builds: Build[]) => void;
  setIsSyncing: (isSyncing: boolean) => void;
  syncWorkItems: (configId: string) => Promise<void>;
  syncRepositories: (configId: string) => Promise<void>;
  syncBuilds: (configId: string) => Promise<void>;
  
  // 对话操作
  setConversations: (conversations: Conversation[]) => void;
  addConversation: (conversation: Conversation) => void;
  updateConversation: (id: string, updates: Partial<Conversation>) => void;
  deleteConversation: (id: string) => void;
  setCurrentConversation: (id?: string) => void;
  addMessage: (conversationId: string, message: Message) => void;
  setIsGenerating: (isGenerating: boolean) => void;
  setInputMessage: (message: string) => void;
  sendMessage: (content: string) => Promise<void>;
  createNewConversation: () => string;
}

// 创建store
export const useAppStore = create<GlobalState>()(
  persist(
    (set, get) => ({
      // 初始状态
      currentView: 'tasks',
      sidebarCollapsed: false,
      theme: 'system',
      user: undefined,
      
      // 知识管理初始状态
      knowledge: {
        notes: [],
        links: [],
        tags: [],
        currentNoteId: undefined,
        searchQuery: '',
        viewMode: 'list',
      },
      
      // 记忆管理初始状态
      memory: {
        memories: [],
        currentQuery: '',
        searchResults: [],
        isSearching: false,
      },
      
      // ClawTeam初始状态
      clawteam: {
        agents: [],
        teams: [],
        tasks: [],
        tools: [],
        currentTeamId: undefined,
        currentTaskId: undefined,
        isExecuting: false,
      },
      
      // Azure DevOps初始状态
      azureDevOps: {
        configs: [],
        currentConfigId: undefined,
        workItems: [],
        repositories: [],
        builds: [],
        isSyncing: false,
        syncStates: {},
      },
      
      // 对话初始状态
      chat: {
        conversations: [],
        currentConversationId: undefined,
        isGenerating: false,
        inputMessage: '',
      },
      
      // ===== 全局操作 =====
      setCurrentView: (view) => set({ currentView: view }),
      toggleSidebar: () => set((state) => ({ 
        sidebarCollapsed: !state.sidebarCollapsed 
      })),
      setTheme: (theme) => set({ theme }),
      setUser: (user) => set({ user }),
      
      // ===== 知识管理操作 =====
      setNotes: (notes) => set((state) => ({ 
        knowledge: { ...state.knowledge, notes } 
      })),
      addNote: (note) => set((state) => ({ 
        knowledge: { 
          ...state.knowledge, 
          notes: [...state.knowledge.notes, note] 
        } 
      })),
      updateNote: (id, updates) => set((state) => ({ 
        knowledge: { 
          ...state.knowledge, 
          notes: state.knowledge.notes.map(n => 
            n.id === id ? { ...n, ...updates, updatedAt: new Date() } : n
          ) 
        } 
      })),
      deleteNote: (id) => set((state) => ({ 
        knowledge: { 
          ...state.knowledge, 
          notes: state.knowledge.notes.filter(n => n.id !== id) 
        } 
      })),
      setCurrentNote: (id) => set((state) => ({ 
        knowledge: { ...state.knowledge, currentNoteId: id } 
      })),
      setSearchQuery: (query) => set((state) => ({ 
        knowledge: { ...state.knowledge, searchQuery: query } 
      })),
      setViewMode: (mode) => set((state) => ({ 
        knowledge: { ...state.knowledge, viewMode: mode } 
      })),
      getNoteById: (id) => get().knowledge.notes.find(n => n.id === id),
      getLinkedNotes: (noteId) => {
        const state = get();
        const linkedIds = state.knowledge.links
          .filter(l => l.sourceNoteId === noteId || l.targetNoteId === noteId)
          .map(l => l.sourceNoteId === noteId ? l.targetNoteId : l.sourceNoteId);
        return state.knowledge.notes.filter(n => linkedIds.includes(n.id));
      },
      getNotesByTag: (tagName) => {
        return get().knowledge.notes.filter(n => 
          n.metadata.tags.includes(tagName) || 
          n.metadata.extractedTags.includes(tagName)
        );
      },
      
      // ===== 记忆管理操作 =====
      setMemories: (memories) => set((state) => ({ 
        memory: { ...state.memory, memories } 
      })),
      addMemory: (memory) => set((state) => ({ 
        memory: { 
          ...state.memory, 
          memories: [...state.memory.memories, memory] 
        } 
      })),
      updateMemory: (id, updates) => set((state) => ({ 
        memory: { 
          ...state.memory, 
          memories: state.memory.memories.map(m => 
            m.id === id ? { ...m, ...updates, metadata: { ...m.metadata, ...updates.metadata, updatedAt: new Date() } } : m
          ) 
        } 
      })),
      deleteMemory: (id) => set((state) => ({ 
        memory: { 
          ...state.memory, 
          memories: state.memory.memories.filter(m => m.id !== id) 
        } 
      })),
      setCurrentQuery: (query) => set((state) => ({ 
        memory: { ...state.memory, currentQuery: query } 
      })),
      setSearchResults: (results) => set((state) => ({ 
        memory: { ...state.memory, searchResults: results } 
      })),
      setIsSearching: (isSearching) => set((state) => ({ 
        memory: { ...state.memory, isSearching } 
      })),
      searchMemories: async (query) => {
        set((state) => ({ memory: { ...state.memory, isSearching: true } }));
        // 模拟搜索 - 实际实现会调用向量数据库
        const memories = get().memory.memories.filter(m => 
          m.content.toLowerCase().includes(query.toLowerCase())
        );
        set((state) => ({ 
          memory: { ...state.memory, searchResults: memories, isSearching: false } 
        }));
        return memories;
      },
      
      // ===== ClawTeam操作 =====
      setAgents: (agents) => set((state) => ({ 
        clawteam: { ...state.clawteam, agents } 
      })),
      addAgent: (agent) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          agents: [...state.clawteam.agents, agent] 
        } 
      })),
      updateAgent: (id, updates) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          agents: state.clawteam.agents.map(a => 
            a.id === id ? { ...a, ...updates } : a
          ) 
        } 
      })),
      deleteAgent: (id) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          agents: state.clawteam.agents.filter(a => a.id !== id) 
        } 
      })),
      setTeams: (teams) => set((state) => ({ 
        clawteam: { ...state.clawteam, teams } 
      })),
      addTeam: (team) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          teams: [...state.clawteam.teams, team] 
        } 
      })),
      updateTeam: (id, updates) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          teams: state.clawteam.teams.map(t => 
            t.id === id ? { ...t, ...updates, updatedAt: new Date() } : t
          ) 
        } 
      })),
      deleteTeam: (id) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          teams: state.clawteam.teams.filter(t => t.id !== id) 
        } 
      })),
      setCurrentTeam: (id) => set((state) => ({ 
        clawteam: { ...state.clawteam, currentTeamId: id } 
      })),
      setTasks: (tasks) => set((state) => ({ 
        clawteam: { ...state.clawteam, tasks } 
      })),
      addTask: (task) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          tasks: [...state.clawteam.tasks, task] 
        } 
      })),
      updateTask: (id, updates) => set((state) => ({ 
        clawteam: { 
          ...state.clawteam, 
          tasks: state.clawteam.tasks.map(t => 
            t.id === id ? { ...t, ...updates } : t
          ) 
        } 
      })),
      setCurrentTask: (id) => set((state) => ({ 
        clawteam: { ...state.clawteam, currentTaskId: id } 
      })),
      setTools: (tools) => set((state) => ({ 
        clawteam: { ...state.clawteam, tools } 
      })),
      setIsExecuting: (isExecuting) => set((state) => ({ 
        clawteam: { ...state.clawteam, isExecuting } 
      })),
      executeTask: async (_teamId, _description) => {
        set((state) => ({ clawteam: { ...state.clawteam, isExecuting: true } }));
        // 模拟任务执行 - 实际实现会调用LLM和代理编排
        await new Promise(resolve => setTimeout(resolve, 2000));
        set((state) => ({ clawteam: { ...state.clawteam, isExecuting: false } }));
      },
      
      // ===== Azure DevOps操作 =====
      setConfigs: (configs) => set((state) => ({ 
        azureDevOps: { ...state.azureDevOps, configs } 
      })),
      addConfig: (config) => set((state) => ({ 
        azureDevOps: { 
          ...state.azureDevOps, 
          configs: [...state.azureDevOps.configs, config] 
        } 
      })),
      updateConfig: (id, updates) => set((state) => ({ 
        azureDevOps: { 
          ...state.azureDevOps, 
          configs: state.azureDevOps.configs.map(c => 
            c.id === id ? { ...c, ...updates, updatedAt: new Date() } : c
          ) 
        } 
      })),
      deleteConfig: (id) => set((state) => ({ 
        azureDevOps: { 
          ...state.azureDevOps, 
          configs: state.azureDevOps.configs.filter(c => c.id !== id) 
        } 
      })),
      setCurrentConfig: (id) => set((state) => ({ 
        azureDevOps: { ...state.azureDevOps, currentConfigId: id } 
      })),
      setWorkItems: (workItems) => set((state) => ({ 
        azureDevOps: { ...state.azureDevOps, workItems } 
      })),
      addWorkItems: (workItems) => set((state) => ({ 
        azureDevOps: { 
          ...state.azureDevOps, 
          workItems: [...state.azureDevOps.workItems, ...workItems] 
        } 
      })),
      setRepositories: (repositories) => set((state) => ({ 
        azureDevOps: { ...state.azureDevOps, repositories } 
      })),
      setBuilds: (builds) => set((state) => ({ 
        azureDevOps: { ...state.azureDevOps, builds } 
      })),
      setIsSyncing: (isSyncing) => set((state) => ({ 
        azureDevOps: { ...state.azureDevOps, isSyncing } 
      })),
      syncWorkItems: async (_configId) => {
        set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: true } }));
        // 模拟同步 - 实际实现会调用Azure DevOps API
        await new Promise(resolve => setTimeout(resolve, 1500));
        set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: false } }));
      },
      syncRepositories: async (_configId) => {
        set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: true } }));
        await new Promise(resolve => setTimeout(resolve, 1500));
        set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: false } }));
      },
      syncBuilds: async (_configId) => {
        set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: true } }));
        await new Promise(resolve => setTimeout(resolve, 1500));
        set((state) => ({ azureDevOps: { ...state.azureDevOps, isSyncing: false } }));
      },
      
      // ===== 对话操作 =====
      setConversations: (conversations) => set((state) => ({ 
        chat: { ...state.chat, conversations } 
      })),
      addConversation: (conversation) => set((state) => ({ 
        chat: { 
          ...state.chat, 
          conversations: [...state.chat.conversations, conversation] 
        } 
      })),
      updateConversation: (id, updates) => set((state) => ({ 
        chat: { 
          ...state.chat, 
          conversations: state.chat.conversations.map(c => 
            c.id === id ? { ...c, ...updates, updatedAt: new Date() } : c
          ) 
        } 
      })),
      deleteConversation: (id) => set((state) => ({ 
        chat: { 
          ...state.chat, 
          conversations: state.chat.conversations.filter(c => c.id !== id),
          currentConversationId: state.chat.currentConversationId === id 
            ? undefined 
            : state.chat.currentConversationId
        } 
      })),
      setCurrentConversation: (id) => set((state) => ({ 
        chat: { ...state.chat, currentConversationId: id } 
      })),
      addMessage: (conversationId, message) => set((state) => ({ 
        chat: { 
          ...state.chat, 
          conversations: state.chat.conversations.map(c => 
            c.id === conversationId 
              ? { ...c, messages: [...c.messages, message], updatedAt: new Date() } 
              : c
          ) 
        } 
      })),
      setIsGenerating: (isGenerating) => set((state) => ({ 
        chat: { ...state.chat, isGenerating } 
      })),
      setInputMessage: (message) => set((state) => ({ 
        chat: { ...state.chat, inputMessage: message } 
      })),
      sendMessage: async (content) => {
        const state = get();
        const conversationId = state.chat.currentConversationId;
        if (!conversationId) return;
        
        // 添加用户消息
        const userMessage: Message = {
          id: Date.now().toString(),
          role: 'user',
          content,
          timestamp: new Date(),
        };
        
        set((state) => ({
          chat: {
            ...state.chat,
            conversations: state.chat.conversations.map(c => 
              c.id === conversationId 
                ? { ...c, messages: [...c.messages, userMessage], updatedAt: new Date() } 
                : c
            ),
            inputMessage: '',
            isGenerating: true,
          }
        }));
        
        // 模拟AI回复 - 实际实现会调用LLM
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        const assistantMessage: Message = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: `我已收到您的消息: "${content}"\n\n这是一个演示回复。在实际实现中，这里会调用LLM生成智能回复，并结合知识库和记忆提供个性化响应。`,
          timestamp: new Date(),
          metadata: {
            model: 'gpt-4',
            tokens: 150,
            latency: 1200,
          }
        };
        
        set((state) => ({
          chat: {
            ...state.chat,
            conversations: state.chat.conversations.map(c => 
              c.id === conversationId 
                ? { ...c, messages: [...c.messages, assistantMessage], updatedAt: new Date() } 
                : c
            ),
            isGenerating: false,
          }
        }));
      },
      createNewConversation: () => {
        const newConversation: Conversation = {
          id: Date.now().toString(),
          title: '新对话',
          messages: [],
          createdAt: new Date(),
          updatedAt: new Date(),
        };
        set((state) => ({
          chat: {
            ...state.chat,
            conversations: [...state.chat.conversations, newConversation],
            currentConversationId: newConversation.id,
          }
        }));
        return newConversation.id;
      },
    }),
    {
      name: 'ai-work-assistant-storage',
      partialize: (state) => ({
        knowledge: {
          notes: state.knowledge.notes,
          links: state.knowledge.links,
          tags: state.knowledge.tags,
        },
        memory: {
          memories: state.memory.memories,
        },
        clawteam: {
          agents: state.clawteam.agents,
          teams: state.clawteam.teams,
          tools: state.clawteam.tools,
        },
        azureDevOps: {
          configs: state.azureDevOps.configs,
        },
        chat: {
          conversations: state.chat.conversations,
        },
        theme: state.theme,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
);
