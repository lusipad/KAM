import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Archive,
  Bot,
  Brain,
  ChevronRight,
  File,
  FileText,
  Folder,
  FolderKanban,
  GitCompareArrows,
  MessageSquare,
  Pin,
  Plus,
  RefreshCcw,
  Save,
  Search,
  Send,
  Sparkles,
  Square,
  Trash2,
  Undo2,
} from 'lucide-react';
import {
  getV2RunEventsUrl,
  getV2ThreadEventsUrl,
  type ThreadMessageStreamEvent,
  v2MemoryApi,
  v2ProjectsApi,
  v2RunsApi,
  v2ThreadsApi,
} from '@/lib/api-v2';
import type {
  BootstrapThreadMessageResponse,
  CompareAgentSpec,
  ConversationRun,
  DecisionRecord,
  PostThreadMessageResponse,
  ProjectFileTreeRecord,
  ProjectLearningRecord,
  ProjectRecord,
  ProjectThread,
  ThreadMessageRecord,
  ThreadRunArtifactRecord,
  UserPreferenceRecord,
} from '@/types/v2';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';

type PanelTab = 'project' | 'memory' | 'detail' | 'compare';

type CompareGroup = {
  compareId: string;
  prompt: string;
  createdAt?: string | Date;
  runs: ConversationRun[];
};

const WORKSPACE_STORAGE_KEY = 'kam.v2.workspace';

function readStoredWorkspaceState(): {
  selectedProjectId?: string | null;
  selectedThreadId?: string | null;
  activePanel?: PanelTab;
} {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as {
      selectedProjectId?: string | null;
      selectedThreadId?: string | null;
      activePanel?: PanelTab;
    };
    return {
      selectedProjectId: typeof parsed.selectedProjectId === 'string' ? parsed.selectedProjectId : null,
      selectedThreadId: typeof parsed.selectedThreadId === 'string' ? parsed.selectedThreadId : null,
      activePanel: parsed.activePanel || 'project',
    };
  } catch {
    return {};
  }
}

function getErrorMessage(error: unknown) {
  return error instanceof Error && error.message ? error.message : '请求失败，请稍后再试。';
}

function fmtTime(value?: string | Date | null) {
  if (!value) return '刚刚';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function runTone(status: string) {
  if (status === 'passed') return 'default';
  if (status === 'failed' || status === 'cancelled') return 'destructive';
  return 'secondary';
}

function isActiveRun(run?: ConversationRun | null) {
  return !!run && ['pending', 'running', 'checking'].includes(run.status);
}

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object';
}

function asRunList(value: unknown): ConversationRun[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is ConversationRun => isRecord(item) && typeof item.id === 'string');
}

function asThreadMessage(value: unknown): ThreadMessageRecord | null {
  if (!isRecord(value)) return null;
  if (typeof value.id !== 'string' || typeof value.content !== 'string') return null;
  return value as unknown as ThreadMessageRecord;
}

function splitCommands(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

const ARTIFACT_TYPE_PRIORITY = ['summary', 'check_result', 'feedback', 'changes', 'patch', 'stdout', 'stderr', 'prompt', 'context'];

function artifactDateValue(value?: string | Date) {
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function sortArtifactTypes(types: string[]) {
  return [...types].sort((left, right) => {
    const leftIndex = ARTIFACT_TYPE_PRIORITY.indexOf(left);
    const rightIndex = ARTIFACT_TYPE_PRIORITY.indexOf(right);
    if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right);
    if (leftIndex === -1) return 1;
    if (rightIndex === -1) return -1;
    return leftIndex - rightIndex;
  });
}

function buildArtifactIndex(artifacts?: ThreadRunArtifactRecord[]) {
  const index: Record<string, ThreadRunArtifactRecord> = {};
  const sorted = [...(artifacts || [])].sort((left, right) => {
    const roundDelta = Number(left.round || 0) - Number(right.round || 0);
    if (roundDelta !== 0) return roundDelta;
    return artifactDateValue(left.createdAt) - artifactDateValue(right.createdAt);
  });
  for (const artifact of sorted) {
    index[artifact.type] = artifact;
  }
  return index;
}

function buildArtifactRounds(artifacts?: ThreadRunArtifactRecord[]) {
  const grouped = new Map<number, ThreadRunArtifactRecord[]>();
  for (const artifact of artifacts || []) {
    const round = Number(artifact.round || 1);
    if (!grouped.has(round)) grouped.set(round, []);
    grouped.get(round)!.push(artifact);
  }
  return Array.from(grouped.entries())
    .sort((left, right) => right[0] - left[0])
    .map(([round, items]) => ({
      round,
      artifacts: items,
      index: buildArtifactIndex(items),
    }));
}

function artifactPreview(content?: string, maxChars = 520) {
  const normalized = (content || '').trim();
  if (!normalized) return '（空）';
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, maxChars)}…`;
}

function fmtDuration(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  if (value < 1000) return `${value}ms`;
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainSeconds}s`;
}

function parseCheckResults(content?: string) {
  try {
    const parsed = JSON.parse(content || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function checkOutputText(item: Record<string, unknown>) {
  return asString(item.stderrPreview) || asString(item.stdoutPreview) || asString(item.output);
}

function summaryText(run?: ConversationRun | null) {
  const artifacts = buildArtifactIndex(run?.artifacts);
  return artifacts.summary?.content?.trim() || run?.error || '暂无摘要';
}

function commandLine(run?: ConversationRun | null) {
  return asString(run?.metadata?.commandLine) || run?.command || '未记录命令';
}

export function WorkspaceView() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() => readStoredWorkspaceState().selectedProjectId ?? null);
  const [selectedProject, setSelectedProject] = useState<ProjectRecord | null>(null);
  const [threads, setThreads] = useState<ProjectThread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(() => readStoredWorkspaceState().selectedThreadId ?? null);
  const [selectedThread, setSelectedThread] = useState<ProjectThread | null>(null);
  const [projectTitle, setProjectTitle] = useState('');
  const [threadTitle, setThreadTitle] = useState('');
  const [messageText, setMessageText] = useState('');
  const [autoRun, setAutoRun] = useState(true);
  const [agent, setAgent] = useState('codex');
  const [customCommand, setCustomCommand] = useState('');
  const [activePanel, setActivePanel] = useState<PanelTab>(() => readStoredWorkspaceState().activePanel ?? 'project');
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRunDetail, setSelectedRunDetail] = useState<ConversationRun | null>(null);
  const [detailRound, setDetailRound] = useState<number | null>(null);
  const [detailArtifactType, setDetailArtifactType] = useState('summary');
  const [selectedCompareId, setSelectedCompareId] = useState<string | null>(null);
  const [compareArtifactType, setCompareArtifactType] = useState('summary');
  const [compareRunDetails, setCompareRunDetails] = useState<Record<string, ConversationRun>>({});

  const [projectForm, setProjectForm] = useState({
    title: '',
    description: '',
    repoPath: '',
    status: 'active',
    checkCommands: '',
  });
  const [resourceForm, setResourceForm] = useState({
    type: 'note',
    title: '',
    uri: '',
    pinned: true,
  });

  const [memoryQuery, setMemoryQuery] = useState('');
  const [preferences, setPreferences] = useState<UserPreferenceRecord[]>([]);
  const [decisions, setDecisions] = useState<DecisionRecord[]>([]);
  const [learnings, setLearnings] = useState<ProjectLearningRecord[]>([]);
  const [preferenceForm, setPreferenceForm] = useState({ category: 'general', key: '', value: '' });
  const [decisionForm, setDecisionForm] = useState({ question: '', decision: '', reasoning: '' });
  const [learningForm, setLearningForm] = useState({ content: '' });
  const [preferenceDrafts, setPreferenceDrafts] = useState<Record<string, string>>({});
  const [decisionDrafts, setDecisionDrafts] = useState<Record<string, { question: string; decision: string; reasoning: string }>>({});
  const [learningDrafts, setLearningDrafts] = useState<Record<string, string>>({});

  const [comparePrompt, setComparePrompt] = useState('');
  const [fileTreePath, setFileTreePath] = useState('');
  const [fileTree, setFileTree] = useState<ProjectFileTreeRecord | null>(null);
  const [fileTreeQuery, setFileTreeQuery] = useState('');
  const [fileTreeEntryType, setFileTreeEntryType] = useState('all');
  const [fileTreeIncludeHidden, setFileTreeIncludeHidden] = useState(false);
  const [compareAgents, setCompareAgents] = useState({ codex: true, claude: true, custom: false });
  const [compareCustomLabel, setCompareCustomLabel] = useState('Custom Command');
  const [compareCustomCommand, setCompareCustomCommand] = useState('');

  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);
  const [isMemoryLoading, setIsMemoryLoading] = useState(false);
  const [isFilesLoading, setIsFilesLoading] = useState(false);
  const [isRunLoading, setIsRunLoading] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [streamingReplyText, setStreamingReplyText] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    void loadProjects();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    void loadProject(selectedProjectId, '');
    void loadMemory(selectedProjectId, memoryQuery);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedThreadId) return;
    void loadThread(selectedThreadId);
  }, [selectedThreadId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(
      WORKSPACE_STORAGE_KEY,
      JSON.stringify({
        selectedProjectId,
        selectedThreadId,
        activePanel,
      }),
    );
  }, [activePanel, selectedProjectId, selectedThreadId]);

  useEffect(() => {
    if (!selectedThreadId) return;

    const eventSource = new EventSource(getV2ThreadEventsUrl(selectedThreadId));
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          thread?: ProjectThread;
          hasActiveRuns?: boolean;
        };
        if (!payload.thread) return;
        const nextThread = payload.thread;
        setSelectedThread(nextThread);
        setThreads((current) => {
          if (current.some((item) => item.id === nextThread.id)) {
            return current.map((item) => (item.id === nextThread.id ? { ...item, ...nextThread } : item));
          }
          return [nextThread, ...current];
        });
        if (!payload.hasActiveRuns) {
          eventSource.close();
        }
      } catch {
        eventSource.close();
      }
    };
    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [selectedThreadId]);

  useEffect(() => {
    if (!selectedProject) return;
    setProjectForm({
      title: selectedProject.title || '',
      description: selectedProject.description || '',
      repoPath: selectedProject.repoPath || '',
      status: selectedProject.status || 'active',
      checkCommands: (selectedProject.checkCommands || []).join('\n'),
    });
  }, [selectedProject]);

  useEffect(() => {
    const nextRuns = selectedThread?.runs || [];
    if (!nextRuns.length) {
      setSelectedRunId(null);
      setSelectedRunDetail(null);
      return;
    }
    if (selectedRunId && nextRuns.some((item) => item.id === selectedRunId)) return;
    setSelectedRunId(nextRuns[0].id);
  }, [selectedThread, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) return;
    void loadRunDetail(selectedRunId);
  }, [selectedRunId]);

  useEffect(() => {
    if (!selectedRunId) return;

    const eventSource = new EventSource(getV2RunEventsUrl(selectedRunId, 60_000));
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as {
          run?: ConversationRun;
          artifacts?: ThreadRunArtifactRecord[];
        };
        if (!payload.run) return;
        setSelectedRunDetail({
          ...payload.run,
          artifacts: payload.artifacts || [],
        });
        if (!isActiveRun(payload.run)) {
          eventSource.close();
        }
      } catch {
        eventSource.close();
      }
    };
    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [selectedRunId]);

  const compareGroups = useMemo<CompareGroup[]>(() => {
    const groupMap = new Map<string, CompareGroup>();
    for (const run of selectedThread?.runs || []) {
      const compareId = asString(run.metadata?.compareGroupId);
      if (!compareId) continue;
      if (!groupMap.has(compareId)) {
        groupMap.set(compareId, {
          compareId,
          prompt: asString(run.metadata?.comparePrompt) || '并发对比',
          createdAt: run.createdAt,
          runs: [],
        });
      }
      groupMap.get(compareId)?.runs.push(run);
    }
    return Array.from(groupMap.values())
      .map((group) => ({
        ...group,
        runs: [...group.runs].sort((left, right) => {
          return new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime();
        }),
      }))
      .sort((left, right) => new Date(right.createdAt || 0).getTime() - new Date(left.createdAt || 0).getTime());
  }, [selectedThread]);

  useEffect(() => {
    if (!compareGroups.length) {
      setSelectedCompareId(null);
      return;
    }
    if (selectedCompareId && compareGroups.some((item) => item.compareId === selectedCompareId)) return;
    setSelectedCompareId(compareGroups[0].compareId);
  }, [compareGroups, selectedCompareId]);

  const selectedCompareGroup = useMemo(
    () => compareGroups.find((item) => item.compareId === selectedCompareId) || null,
    [compareGroups, selectedCompareId],
  );

  useEffect(() => {
    if (!selectedCompareGroup) return;

    let cancelled = false;
    const eventSources: EventSource[] = [];
    const loadCompareRuns = async () => {
      const results = await Promise.all(
        selectedCompareGroup.runs.map(async (run) => {
          try {
            return await v2RunsApi.getById(run.id);
          } catch {
            return null;
          }
        }),
      );
      if (cancelled) return;
      setCompareRunDetails((current) => {
        const next = { ...current };
        results.forEach((result) => {
          if (result) next[result.id] = result;
        });
        return next;
      });
    };

    void loadCompareRuns();
    selectedCompareGroup.runs.forEach((run) => {
      if (!isActiveRun(run)) {
        return;
      }

      const eventSource = new EventSource(getV2RunEventsUrl(run.id, 60_000));
      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as {
            run?: ConversationRun;
            artifacts?: ThreadRunArtifactRecord[];
          };
          if (!payload.run) return;
          const nextRun: ConversationRun = {
            ...payload.run,
            artifacts: payload.artifacts || [],
          };
          setCompareRunDetails((current) => ({
            ...current,
            [nextRun.id]: nextRun,
          }));
          if (!isActiveRun(nextRun)) {
            eventSource.close();
          }
        } catch {
          eventSource.close();
        }
      };
      eventSource.onerror = () => {
        eventSource.close();
      };
      eventSources.push(eventSource);
    });

    return () => {
      cancelled = true;
      eventSources.forEach((eventSource) => eventSource.close());
    };
  }, [selectedCompareGroup]);

  const pinnedResources = useMemo(() => selectedProject?.pinnedResources || [], [selectedProject]);
  const allResources = useMemo(() => selectedProject?.resources || [], [selectedProject]);
  const activeRuns = useMemo(() => selectedThread?.runs || [], [selectedThread]);
  const runningRunCount = useMemo(() => activeRuns.filter((run) => isActiveRun(run)).length, [activeRuns]);
  const detailRounds = useMemo(() => buildArtifactRounds(selectedRunDetail?.artifacts), [selectedRunDetail]);
  const selectedDetailRoundGroup = useMemo(
    () => detailRounds.find((item) => item.round === detailRound) || detailRounds[0] || null,
    [detailRound, detailRounds],
  );
  const artifactIndex = useMemo(() => buildArtifactIndex(selectedDetailRoundGroup?.artifacts), [selectedDetailRoundGroup]);
  const artifactTypes = useMemo(() => sortArtifactTypes(Object.keys(artifactIndex)), [artifactIndex]);
  const selectedArtifact = artifactIndex[detailArtifactType];
  const selectedCheckResults = parseCheckResults(artifactIndex.check_result?.content);
  const compareArtifactTypes = useMemo(() => {
    if (!selectedCompareGroup) return [];
    const types = new Set<string>();
    selectedCompareGroup.runs.forEach((run) => {
      const detailRun = compareRunDetails[run.id] || run;
      Object.keys(buildArtifactIndex(detailRun.artifacts)).forEach((type) => types.add(type));
    });
    return sortArtifactTypes(Array.from(types));
  }, [compareRunDetails, selectedCompareGroup]);
  const compareActiveRunCount = useMemo(
    () => (selectedCompareGroup?.runs || []).filter((run) => isActiveRun(compareRunDetails[run.id] || run)).length,
    [compareRunDetails, selectedCompareGroup],
  );

  useEffect(() => {
    if (!detailRounds.length) {
      setDetailRound(null);
      return;
    }
    if (!detailRound || !detailRounds.some((item) => item.round === detailRound)) {
      setDetailRound(detailRounds[0].round);
    }
  }, [detailRound, detailRounds]);

  useEffect(() => {
    if (!artifactTypes.length) {
      setDetailArtifactType('summary');
      return;
    }
    if (!artifactTypes.includes(detailArtifactType)) {
      setDetailArtifactType(artifactTypes[0]);
    }
  }, [artifactTypes, detailArtifactType]);

  useEffect(() => {
    if (!compareArtifactTypes.length) {
      setCompareArtifactType('summary');
      return;
    }
    if (!compareArtifactTypes.includes(compareArtifactType)) {
      setCompareArtifactType(compareArtifactTypes[0]);
    }
  }, [compareArtifactType, compareArtifactTypes]);

  async function loadProjects() {
    setIsLoading(true);
    try {
      setErrorMessage(null);
      const response = await v2ProjectsApi.list();
      const nextProjects = response.projects || [];
      setProjects(nextProjects);
      const nextProjectId = selectedProjectId && nextProjects.some((item) => item.id === selectedProjectId)
        ? selectedProjectId
        : nextProjects[0]?.id || null;
      setSelectedProjectId(nextProjectId);
      if (!nextProjectId) {
        setSelectedProject(null);
        setThreads([]);
        setSelectedThreadId(null);
        setSelectedThread(null);
        setFileTree(null);
        setFileTreePath('');
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }

  async function loadProject(projectId: string, nextFilePath: string | null = null) {
    try {
      setErrorMessage(null);
      const project = await v2ProjectsApi.getById(projectId);
      setSelectedProject(project);
      const nextThreads = project.threads || [];
      setThreads(nextThreads);
      const nextThreadId = selectedThreadId && nextThreads.some((item) => item.id === selectedThreadId)
        ? selectedThreadId
        : nextThreads[0]?.id || null;
      setSelectedThreadId(nextThreadId);
      if (!nextThreadId) {
        setSelectedThread(null);
      }
      setProjects((current) => current.map((item) => (item.id === project.id ? { ...item, ...project } : item)));
      if (project.repoPath) {
        await loadProjectFiles(project.id, nextFilePath ?? fileTreePath);
      } else {
        setFileTree(null);
        setFileTreePath('');
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function loadThread(threadId: string) {
    try {
      setErrorMessage(null);
      const thread = await v2ThreadsApi.getById(threadId);
      setSelectedThread(thread);
      setThreads((current) => current.map((item) => (item.id === thread.id ? { ...item, ...thread } : item)));
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function loadMemory(projectId: string, query: string) {
    setIsMemoryLoading(true);
    try {
      setErrorMessage(null);
      if (query.trim()) {
        const response = await v2MemoryApi.search({ query: query.trim(), project_id: projectId });
        setPreferences(response.preferences || []);
        setDecisions(response.decisions || []);
        setLearnings(response.learnings || []);
        const nextDrafts: Record<string, string> = {};
        (response.preferences || []).forEach((item) => {
          nextDrafts[item.id] = item.value;
        });
        setPreferenceDrafts(nextDrafts);
        const nextDecisionDrafts: Record<string, { question: string; decision: string; reasoning: string }> = {};
        (response.decisions || []).forEach((item) => {
          nextDecisionDrafts[item.id] = {
            question: item.question,
            decision: item.decision,
            reasoning: item.reasoning || '',
          };
        });
        setDecisionDrafts(nextDecisionDrafts);
        const nextLearningDrafts: Record<string, string> = {};
        (response.learnings || []).forEach((item) => {
          nextLearningDrafts[item.id] = item.content;
        });
        setLearningDrafts(nextLearningDrafts);
        return;
      }

      const [preferencesResponse, decisionsResponse, learningsResponse] = await Promise.all([
        v2MemoryApi.listPreferences(),
        v2MemoryApi.listDecisions({ project_id: projectId }),
        v2MemoryApi.listLearnings({ project_id: projectId }),
      ]);
      setPreferences(preferencesResponse.preferences || []);
      setDecisions(decisionsResponse.decisions || []);
      setLearnings(learningsResponse.learnings || []);
      const nextDrafts: Record<string, string> = {};
      (preferencesResponse.preferences || []).forEach((item) => {
        nextDrafts[item.id] = item.value;
      });
      setPreferenceDrafts(nextDrafts);
      const nextDecisionDrafts: Record<string, { question: string; decision: string; reasoning: string }> = {};
      (decisionsResponse.decisions || []).forEach((item) => {
        nextDecisionDrafts[item.id] = {
          question: item.question,
          decision: item.decision,
          reasoning: item.reasoning || '',
        };
      });
      setDecisionDrafts(nextDecisionDrafts);
      const nextLearningDrafts: Record<string, string> = {};
      (learningsResponse.learnings || []).forEach((item) => {
        nextLearningDrafts[item.id] = item.content;
      });
      setLearningDrafts(nextLearningDrafts);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMemoryLoading(false);
    }
  }

  async function loadProjectFiles(
    projectId: string,
    path = '',
    options?: { query?: string; entryType?: string; includeHidden?: boolean },
  ) {
    setIsFilesLoading(true);
    try {
      setErrorMessage(null);
      const query = options?.query ?? fileTreeQuery;
      const entryType = options?.entryType ?? fileTreeEntryType;
      const includeHidden = options?.includeHidden ?? fileTreeIncludeHidden;
      const tree = await v2ProjectsApi.listFiles(projectId, {
        path,
        include_hidden: includeHidden,
        query: query.trim() || undefined,
        entry_type: entryType !== 'all' ? entryType : undefined,
      });
      setFileTree(tree);
      setFileTreePath(tree.currentPath || '');
    } catch (error) {
      setFileTree(null);
      setFileTreePath('');
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsFilesLoading(false);
    }
  }

  async function loadRunDetail(runId: string) {
    setIsRunLoading(true);
    try {
      setErrorMessage(null);
      const run = await v2RunsApi.getById(runId);
      setSelectedRunDetail(run);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsRunLoading(false);
    }
  }

  function applyThreadMessageStreamEvent(event: ThreadMessageStreamEvent) {
    const payload = event.data;
    if (!isRecord(payload)) {
      return;
    }

    const delta = asString(payload.replyDelta) || asString(payload.delta);
    if (delta) {
      setStreamingReplyText((current) => current + delta);
    }

    const reply = asThreadMessage(payload.reply);
    if (reply?.content) {
      setStreamingReplyText(reply.content);
    }

    const streamThread = payload.thread;
    if (isRecord(streamThread) && typeof streamThread.id === 'string') {
      const nextThread = streamThread as unknown as ProjectThread;
      setSelectedThread(nextThread);
      setThreads((current) => {
        if (current.some((item) => item.id === nextThread.id)) {
          return current.map((item) => (item.id === nextThread.id ? { ...item, ...nextThread } : item));
        }
        return [nextThread, ...current];
      });
    }

    const runs = asRunList(payload.runs);
    if (runs.length) {
      setSelectedRunId(runs[0].id);
      const nextCompareId = asString(payload.compareId) || asString(runs[0].metadata?.compareGroupId);
      if (nextCompareId) {
        setSelectedCompareId(nextCompareId);
        setActivePanel('compare');
      } else {
        setActivePanel('detail');
      }
    }
  }

  async function handleCreateProject() {
    if (!projectTitle.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      const created = await v2ProjectsApi.create({
        title: projectTitle.trim(),
        description: 'KAM 项目',
      });
      setProjectTitle('');
      await loadProjects();
      setSelectedProjectId(created.id);
      setActivePanel('project');
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleCreateThread() {
    if (!selectedProjectId) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      const created = await v2ThreadsApi.create(selectedProjectId, {
        title: threadTitle.trim() || '新对话',
      });
      setThreadTitle('');
      await loadProject(selectedProjectId, '');
      setSelectedThreadId(created.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSendMessage() {
    const draftMessage = messageText.trim();
    if (!draftMessage) return;
    setIsMutating(true);
    setIsSendingMessage(true);
    try {
      setErrorMessage(null);
      setStreamingReplyText('');

      const command = agent === 'custom' ? customCommand.trim() || undefined : undefined;
      const model = agent === 'codex' ? 'gpt-5.4' : undefined;
      const reasoningEffort = agent === 'codex' ? 'xhigh' : undefined;

      let nextProjectId = selectedProjectId;
      let nextThreadId = selectedThreadId;
      let response: PostThreadMessageResponse | BootstrapThreadMessageResponse;

      if (!selectedProjectId) {
        const bootstrapResponse = await v2ThreadsApi.bootstrapMessage({
          content: draftMessage,
          createRun: autoRun,
          agent,
          command,
          model,
          reasoningEffort,
          projectTitle: projectTitle.trim() || undefined,
          threadTitle: threadTitle.trim() || undefined,
        });
        response = bootstrapResponse;
        nextProjectId = bootstrapResponse.project.id;
        nextThreadId = bootstrapResponse.thread.id;
        setSelectedProjectId(nextProjectId);
        setSelectedThreadId(nextThreadId);
        setProjectTitle('');
        setThreadTitle('');
      } else {
        if (!selectedThreadId) {
          const createdThread = await v2ThreadsApi.create(selectedProjectId, {
            title: threadTitle.trim() || '新对话',
          });
          nextThreadId = createdThread.id;
          setSelectedThreadId(nextThreadId);
          setThreadTitle('');
        }

        const streamedResponse = await v2ThreadsApi.postMessageStream(nextThreadId as string, {
          content: draftMessage,
          createRun: autoRun,
          agent,
          command,
          model,
          reasoningEffort,
        }, {
          onEvent: applyThreadMessageStreamEvent,
        });
        response = streamedResponse || await v2ThreadsApi.postMessage(nextThreadId as string, {
          content: draftMessage,
          createRun: autoRun,
          agent,
          command,
          model,
          reasoningEffort,
        });
      }

      setMessageText('');
      if (agent === 'custom') setCustomCommand('');
      if (response.runs?.length) {
        setSelectedRunId(response.runs[0].id);
        const nextCompareId = asString(response.compareId) || asString(response.runs[0].metadata?.compareGroupId);
        if (nextCompareId) {
          setSelectedCompareId(nextCompareId);
          setActivePanel('compare');
        } else {
          setActivePanel('detail');
        }
      }
      if (nextThreadId) {
        await loadThread(nextThreadId);
      }
      if (nextProjectId) {
        await loadProject(nextProjectId, fileTreePath);
        await loadMemory(nextProjectId, memoryQuery);
      }
      setStreamingReplyText('');
    } catch (error) {
      setMessageText(draftMessage);
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsSendingMessage(false);
      setIsMutating(false);
    }
  }

  async function handleSaveProject() {
    if (!selectedProjectId || !projectForm.title.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2ProjectsApi.update(selectedProjectId, {
        title: projectForm.title.trim(),
        description: projectForm.description.trim(),
        repoPath: projectForm.repoPath.trim() || null,
        status: projectForm.status,
        checkCommands: splitCommands(projectForm.checkCommands),
      });
      await loadProject(selectedProjectId, fileTreePath);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleArchiveProject() {
    if (!selectedProjectId) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2ProjectsApi.archive(selectedProjectId);
      await loadProjects();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleAddResource() {
    if (!selectedProjectId || !resourceForm.uri.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2ProjectsApi.addResource(selectedProjectId, {
        type: resourceForm.type,
        title: resourceForm.title.trim() || undefined,
        uri: resourceForm.uri.trim(),
        pinned: resourceForm.pinned,
      });
      setResourceForm({ type: 'note', title: '', uri: '', pinned: true });
      await loadProject(selectedProjectId, fileTreePath);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleDeleteResource(resourceId: string) {
    if (!selectedProjectId) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2ProjectsApi.deleteResource(selectedProjectId, resourceId);
      await loadProject(selectedProjectId, fileTreePath);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handlePinRepoEntry(relativePath: string, entryName: string) {
    if (!selectedProjectId || !selectedProject?.repoPath) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      const fullPath = relativePath ? `${selectedProject.repoPath}/${relativePath}` : selectedProject.repoPath;
      await v2ProjectsApi.addResource(selectedProjectId, {
        type: 'repo-path',
        title: entryName,
        uri: fullPath,
        pinned: true,
      });
      await loadProject(selectedProjectId, fileTreePath);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleCreatePreference() {
    if (!preferenceForm.key.trim() || !preferenceForm.value.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2MemoryApi.createPreference({
        category: preferenceForm.category.trim() || 'general',
        key: preferenceForm.key.trim(),
        value: preferenceForm.value.trim(),
        sourceThreadId: selectedThreadId || undefined,
      });
      setPreferenceForm({ category: 'general', key: '', value: '' });
      if (selectedProjectId) {
        await loadMemory(selectedProjectId, memoryQuery);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSavePreference(preferenceId: string) {
    const nextValue = (preferenceDrafts[preferenceId] || '').trim();
    if (!nextValue) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2MemoryApi.updatePreference(preferenceId, {
        value: nextValue,
        sourceThreadId: selectedThreadId || undefined,
      });
      if (selectedProjectId) {
        await loadMemory(selectedProjectId, memoryQuery);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleCreateDecision() {
    if (!selectedProjectId || !decisionForm.question.trim() || !decisionForm.decision.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2MemoryApi.createDecision({
        projectId: selectedProjectId,
        question: decisionForm.question.trim(),
        decision: decisionForm.decision.trim(),
        reasoning: decisionForm.reasoning.trim(),
        sourceThreadId: selectedThreadId || undefined,
      });
      setDecisionForm({ question: '', decision: '', reasoning: '' });
      await loadMemory(selectedProjectId, memoryQuery);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleCreateLearning() {
    if (!selectedProjectId || !learningForm.content.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2MemoryApi.createLearning({
        projectId: selectedProjectId,
        content: learningForm.content.trim(),
        sourceThreadId: selectedThreadId || undefined,
      });
      setLearningForm({ content: '' });
      await loadMemory(selectedProjectId, memoryQuery);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSaveDecision(decisionId: string) {
    const draft = decisionDrafts[decisionId];
    if (!draft || !draft.question.trim() || !draft.decision.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2MemoryApi.updateDecision(decisionId, {
        question: draft.question.trim(),
        decision: draft.decision.trim(),
        reasoning: draft.reasoning.trim(),
        sourceThreadId: selectedThreadId || undefined,
      });
      if (selectedProjectId) {
        await loadMemory(selectedProjectId, memoryQuery);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSaveLearning(learningId: string) {
    const content = (learningDrafts[learningId] || '').trim();
    if (!content) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2MemoryApi.updateLearning(learningId, {
        content,
        sourceThreadId: selectedThreadId || undefined,
      });
      if (selectedProjectId) {
        await loadMemory(selectedProjectId, memoryQuery);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleRunCompare() {
    if (!selectedThreadId) return;
    const prompt = comparePrompt.trim() || messageText.trim();
    if (!prompt) {
      setErrorMessage('请先输入要对比的任务描述。');
      return;
    }

    const agents: CompareAgentSpec[] = [];
    if (compareAgents.codex) {
      agents.push({
        agent: 'codex',
        label: 'Codex',
        model: 'gpt-5.4',
        reasoningEffort: 'xhigh',
      });
    }
    if (compareAgents.claude) {
      agents.push({
        agent: 'claude-code',
        label: 'Claude Code',
      });
    }
    if (compareAgents.custom) {
      if (!compareCustomCommand.trim()) {
        setErrorMessage('勾选 Custom 后需要填写命令。');
        return;
      }
      agents.push({
        agent: 'custom',
        label: compareCustomLabel.trim() || 'Custom Command',
        command: compareCustomCommand.trim(),
      });
    }
    if (agents.length < 2) {
      setErrorMessage('至少选择两个方案才能对比。');
      return;
    }

    setIsMutating(true);
    try {
      setErrorMessage(null);
      const response = await v2RunsApi.compare(selectedThreadId, {
        prompt,
        agents,
        autoStart: true,
        maxRounds: 5,
        metadata: {
          requestedFrom: 'kam-compare-panel',
        },
      });
      setComparePrompt('');
      setSelectedCompareId(response.compareId);
      if (response.runs?.length) {
        setSelectedRunId(response.runs[0].id);
      }
      setActivePanel('compare');
      await loadThread(selectedThreadId);
      if (selectedProjectId) {
        await loadProject(selectedProjectId, fileTreePath);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleAdoptRun(runId: string) {
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2RunsApi.adopt(runId);
      if (selectedThreadId) {
        await loadThread(selectedThreadId);
      }
      if (selectedRunId === runId) {
        await loadRunDetail(runId);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleCancelRun(runId: string) {
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2RunsApi.cancel(runId);
      if (selectedThreadId) {
        await loadThread(selectedThreadId);
      }
      if (selectedRunId === runId) {
        await loadRunDetail(runId);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleRetryRun(runId: string) {
    setIsMutating(true);
    try {
      setErrorMessage(null);
      const response = await v2RunsApi.retry(runId);
      setSelectedRunId(response.id);
      const compareId = asString(response.metadata?.compareGroupId);
      if (compareId) {
        setSelectedCompareId(compareId);
      }
      if (selectedThreadId) {
        await loadThread(selectedThreadId);
      }
      setActivePanel(compareId ? 'compare' : 'detail');
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  return (
    <div className="grid min-h-[calc(100dvh-2rem)] gap-4 xl:grid-cols-[280px_minmax(0,1fr)_380px]">
      <section className="rounded-[1.75rem] border border-border/70 bg-card/70 p-4 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/12 text-primary">
            <FolderKanban className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold">Projects</div>
            <div className="text-xs text-muted-foreground">持续上下文与线程导航</div>
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          <Input value={projectTitle} onChange={(event) => setProjectTitle(event.target.value)} placeholder="新项目标题" />
          <Button size="icon" onClick={() => void handleCreateProject()} disabled={isMutating}>
            <Plus className="h-4 w-4" />
          </Button>
        </div>

        <div className="mt-4 space-y-2">
          {projects.map((project) => (
            <button
              key={project.id}
              type="button"
              onClick={() => setSelectedProjectId(project.id)}
              className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                selectedProjectId === project.id
                  ? 'border-primary/50 bg-primary/8 shadow-[0_12px_28px_rgba(202,99,49,0.12)]'
                  : 'border-border/60 bg-background/60 hover:border-primary/30'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="truncate text-sm font-medium">{project.title}</div>
                <div className="flex items-center gap-2">
                  {project.status === 'active' ? <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" /> : null}
                  <Badge variant="outline">{project.status}</Badge>
                </div>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {project.threadCount} 个线程 · {project.resourceCount} 个资源
              </div>
              {project.repoPath ? <div className="mt-1 truncate text-[11px] text-muted-foreground">{project.repoPath}</div> : null}
            </button>
          ))}
          {!projects.length && !isLoading && (
            <div className="rounded-2xl border border-dashed border-border/60 px-3 py-5 text-sm text-muted-foreground">
              你可以先在这里手动建 Project，也可以直接在中间输入第一条任务开始。
            </div>
          )}
        </div>

        <div className="mt-6 border-t border-border/60 pt-4">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold">Threads</div>
              <div className="text-xs text-muted-foreground">项目内连续工作流</div>
            </div>
            <Badge variant="secondary">{threads.length}</Badge>
          </div>

          <div className="mt-3 flex gap-2">
            <Input value={threadTitle} onChange={(event) => setThreadTitle(event.target.value)} placeholder="新线程标题" disabled={!selectedProjectId} />
            <Button size="icon" onClick={() => void handleCreateThread()} disabled={!selectedProjectId || isMutating}>
              <Plus className="h-4 w-4" />
            </Button>
          </div>

          <div className="mt-3 space-y-2">
            {threads.map((thread) => (
              <button
                key={thread.id}
                type="button"
                onClick={() => setSelectedThreadId(thread.id)}
                className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                  selectedThreadId === thread.id ? 'border-primary/40 bg-primary/8' : 'border-border/60 bg-background/60'
                }`}
              >
                <div className="truncate text-sm font-medium">{thread.title}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {thread.messageCount} 条消息 · {fmtTime(thread.updatedAt)}
                </div>
              </button>
            ))}
            {!!selectedProjectId && !threads.length && <div className="text-xs text-muted-foreground">还没有线程，也可以直接在中间输入任务自动创建。</div>}
          </div>
        </div>
      </section>

      <section className="flex min-h-[70dvh] flex-col rounded-[1.75rem] border border-border/70 bg-card/70 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="flex items-center justify-between gap-4 border-b border-border/60 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/12 text-primary">
              <MessageSquare className="h-5 w-5" />
            </div>
            <div>
              <div className="text-base font-semibold">{selectedThread?.title || 'KAM 对话区'}</div>
              <div className="text-xs text-muted-foreground">
                {selectedProject?.title ? `${selectedProject.title} · ` : ''}Project / Thread / Run / Memory 指挥台
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            Codex 默认模型 `gpt-5.4` · `xhigh`
          </div>
        </div>

        <div className="border-b border-border/60 px-5 py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Badge variant="secondary">{activeRuns.length} Runs</Badge>
            <Badge variant="secondary">{compareGroups.length} Compare Sessions</Badge>
            <Badge variant="secondary">{pinnedResources.length} Pinned Resources</Badge>
            <Badge variant="secondary">{preferences.length} Preferences</Badge>
          </div>
          {!!compareGroups.length && (
            <div className="mt-3 flex flex-wrap gap-2">
              {compareGroups.map((group) => (
                <button
                  key={group.compareId}
                  type="button"
                  onClick={() => {
                    setSelectedCompareId(group.compareId);
                    setActivePanel('compare');
                  }}
                  className={`rounded-full border px-3 py-1 text-xs transition ${
                    selectedCompareId === group.compareId ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/60 bg-background/70'
                  }`}
                >
                  {group.runs.length} 路对比 · {fmtTime(group.createdAt)}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          {errorMessage && <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">{errorMessage}</div>}

          {!selectedThread && (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-3 rounded-[1.75rem] border border-dashed border-border/60 bg-background/40 text-center">
              <Bot className="h-8 w-8 text-primary" />
              <div className="text-base font-semibold">直接开始对话或选择现有 Project / Thread</div>
              <div className="max-w-md text-sm text-muted-foreground">
                这一版已经切到 v2 心智：Project 管持续上下文，Thread 管连续对话。你现在可以直接输入第一条消息，系统会自动创建 Project、Thread，并把 Run 内联展示。
              </div>
            </div>
          )}

          {!!selectedThread && !selectedThread.messages?.length && (
            <div className="rounded-[1.75rem] border border-dashed border-border/60 bg-background/40 px-5 py-8 text-center text-sm text-muted-foreground">
              这个 Thread 还没有消息，直接输入任务开始即可；如果还没选中 Thread，也可以直接输入让系统自动创建。
            </div>
          )}

          {selectedThread?.messages?.map((message: ThreadMessageRecord) => {
            const systemEventType = asString(message.metadata?.eventType);
            const systemEventStatus = asString(message.metadata?.status);
            const isSystemEvent = message.role === 'system' && !!systemEventType;
            const bubbleClass = message.role === 'user'
              ? 'bg-primary text-primary-foreground'
              : message.role === 'system'
                ? 'border border-primary/20 bg-primary/5'
                : 'border border-border/60 bg-background/70';

            const renderRuns = !!message.runs?.length && (
              <div className="mt-3 space-y-2">
                {message.runs.map((run) => (
                  <RunInlineCard
                    key={run.id}
                    run={run}
                    selected={selectedRunId === run.id}
                    onSelect={() => {
                      setSelectedRunId(run.id);
                      const compareId = asString(run.metadata?.compareGroupId);
                      if (compareId) setSelectedCompareId(compareId);
                      setActivePanel(compareId ? 'compare' : 'detail');
                    }}
                    onAdopt={() => void handleAdoptRun(run.id)}
                    onCancel={() => void handleCancelRun(run.id)}
                    onRetry={() => void handleRetryRun(run.id)}
                  />
                ))}
              </div>
            );

            if (isSystemEvent) {
              const eventLabel = ({
                'run-created': 'Run Created',
                'compare-created': 'Compare',
                'run-started': 'Running',
                'run-checking': 'Checking',
                'run-retrying': 'Retrying',
                'run-passed': 'Passed',
                'run-failed': 'Failed',
                'run-cancelled': 'Cancelled',
              } as Record<string, string>)[systemEventType] || 'System';
              const round = typeof message.metadata?.round === 'number' ? `R${message.metadata.round}` : '';
              return (
                <div key={message.id} className="flex justify-start">
                  <div className="max-w-[82%] rounded-[1.5rem] border border-border/60 bg-background/70 px-4 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={runTone(systemEventStatus || 'pending')}>{eventLabel}</Badge>
                      {asString(message.metadata?.agent) ? <Badge variant="outline">{asString(message.metadata?.agent)}</Badge> : null}
                      {round ? <Badge variant="outline">{round}</Badge> : null}
                      <div className="text-[11px] text-muted-foreground">{fmtTime(message.createdAt)}</div>
                    </div>
                    <div className="mt-2 whitespace-pre-wrap text-sm leading-6">{message.content}</div>
                    {renderRuns}
                  </div>
                </div>
              );
            }

            return (
              <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[82%] rounded-[1.6rem] px-4 py-3 ${bubbleClass}`}>
                  <div className="text-[11px] uppercase tracking-[0.22em] opacity-70">{message.role}</div>
                  <div className="mt-2 whitespace-pre-wrap text-sm leading-6">{message.content}</div>
                  <div className="mt-2 text-[11px] opacity-70">{fmtTime(message.createdAt)}</div>
                  {renderRuns}
                </div>
              </div>
            );
          })}
          {isSendingMessage && streamingReplyText ? (
            <div className="flex justify-start">
              <div className="max-w-[82%] rounded-[1.6rem] border border-border/60 bg-background/70 px-4 py-3">
                <div className="text-[11px] uppercase tracking-[0.22em] opacity-70">assistant</div>
                <div className="mt-2 whitespace-pre-wrap text-sm leading-6">{streamingReplyText}</div>
                <div className="mt-2 text-[11px] text-muted-foreground">流式生成中...</div>
              </div>
            </div>
          ) : null}
        </div>

        <div className="border-t border-border/60 px-5 py-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_240px]">
            <div className="space-y-3">
              <Textarea
                value={messageText}
                onChange={(event) => setMessageText(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key !== 'Enter') return;
                  if (!event.metaKey && !event.ctrlKey) return;
                  event.preventDefault();
                  if (isMutating || (agent === 'custom' && !customCommand.trim())) return;
                  void handleSendMessage();
                }}
                placeholder={!selectedProjectId
                  ? "直接描述你的目标，我会先为你创建 Project 和 Thread。"
                  : !selectedThreadId
                    ? "直接输入任务，我会先为当前 Project 创建 Thread。"
                    : "比如：继续昨天的工作，先把 OAuth token refresh 做完。"}
                className="min-h-[112px] rounded-[1.3rem]"
                disabled={isMutating}
              />
              <div className="flex items-center justify-between gap-3 rounded-[1.2rem] border border-border/60 bg-background/50 px-3 py-2 text-xs text-muted-foreground">
                <div>
                  {isSendingMessage
                    ? '消息发送中，正在接收流式回复...'
                    : '这里既能继续当前 Thread，也能在空白状态下直接启动新的 Project / Thread。'}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setComparePrompt(messageText);
                    setActivePanel('compare');
                  }}
                  disabled={!messageText.trim() || isSendingMessage}
                >
                  <GitCompareArrows className="mr-1 h-3.5 w-3.5" />
                  带去对比
                </Button>
              </div>
            </div>

            <div className="space-y-3 rounded-[1.3rem] border border-border/60 bg-background/60 p-3">
              <label className="block space-y-2 text-sm">
                <span className="text-muted-foreground">Agent</span>
                <select
                  value={agent}
                  onChange={(event) => setAgent(event.target.value)}
                  className="h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                >
                  <option value="codex">Codex</option>
                  <option value="claude-code">Claude Code</option>
                  <option value="custom">Custom Command</option>
                </select>
              </label>
              {agent === 'custom' ? (
                <label className="block space-y-2 text-sm">
                  <span className="text-muted-foreground">Custom Command</span>
                  <Textarea
                    value={customCommand}
                    onChange={(event) => setCustomCommand(event.target.value)}
                    placeholder="例如：pytest -q 或 bash -lc 'npm test'"
                    className="min-h-[96px] rounded-xl"
                  />
                </label>
              ) : null}
              <label className="flex items-center gap-2 text-sm text-muted-foreground">
                <input type="checkbox" checked={autoRun} onChange={(event) => setAutoRun(event.target.checked)} />
                发送时自动创建 Run
              </label>
              <Button
                className="w-full rounded-xl"
                onClick={() => void handleSendMessage()}
                disabled={!messageText.trim() || isMutating || (agent === 'custom' && !customCommand.trim())}
              >
                <Send className="mr-2 h-4 w-4" />
                {isSendingMessage ? '发送中...' : !selectedProjectId ? '开始新项目' : !selectedThreadId ? '开始新线程' : '发送到 Thread'}
              </Button>
              <div className="text-[11px] text-muted-foreground">快捷键：Cmd/Ctrl + Enter 发送</div>
            </div>
          </div>
        </div>

        <div className="border-t border-border/60 px-5 py-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Status:</span>
            <span>{runningRunCount ? `${runningRunCount} runs active` : '当前没有活跃 runs'}</span>
            <span>·</span>
            <span>{selectedProject?.title || '未选择 Project'}</span>
            <span>·</span>
            <span>{selectedThread?.title || '未选择 Thread'}</span>
            <span>·</span>
            <span>{autoRun ? '发送即执行' : '仅对话模式'}</span>
            <span>·</span>
            <span>{agent === 'codex' ? 'Codex · gpt-5.4 / xhigh' : agent === 'claude-code' ? 'Claude Code' : 'Custom Command'}</span>
            {selectedCompareGroup ? (
              <>
                <span>·</span>
                <span>{selectedCompareGroup.runs.length} 路 Compare / {compareActiveRunCount} active</span>
              </>
            ) : null}
          </div>
        </div>
      </section>

      <aside className="rounded-[1.75rem] border border-border/70 bg-card/70 p-4 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur">
        <Tabs value={activePanel} onValueChange={(value) => setActivePanel(value as PanelTab)} className="flex h-full min-h-[70dvh] flex-col">
          <div>
            <div className="text-sm font-semibold">Context Panel</div>
            <div className="mt-1 text-xs text-muted-foreground">项目设置、记忆、Run 详情与多 Agent 对比</div>
          </div>

          <TabsList className="mt-4 grid w-full grid-cols-4 rounded-2xl border border-border/60 bg-background/70 p-1">
            <TabsTrigger value="project" className="rounded-xl text-xs">Project</TabsTrigger>
            <TabsTrigger value="memory" className="rounded-xl text-xs">Memory</TabsTrigger>
            <TabsTrigger value="detail" className="rounded-xl text-xs">Detail</TabsTrigger>
            <TabsTrigger value="compare" className="rounded-xl text-xs">Compare</TabsTrigger>
          </TabsList>

          <TabsContent value="project" className="mt-4 flex-1 overflow-y-auto">
            {!selectedProject ? (
              <PanelEmpty icon={<FolderKanban className="h-5 w-5" />} title="还没有选中项目" description="先在左侧选一个 Project，再编辑设置与资源。" />
            ) : (
              <div className="space-y-5 pr-1">
                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">Project Settings</div>
                      <div className="mt-1 text-xs text-muted-foreground">配置描述、仓库路径和项目级检查命令</div>
                    </div>
                    <Badge variant="secondary">{selectedProject.status}</Badge>
                  </div>
                  <div className="mt-4 space-y-3">
                    <Input value={projectForm.title} onChange={(event) => setProjectForm((current) => ({ ...current, title: event.target.value }))} placeholder="项目标题" />
                    <Input value={projectForm.repoPath} onChange={(event) => setProjectForm((current) => ({ ...current, repoPath: event.target.value }))} placeholder="仓库路径，例如 /workspace/repo" />
                    <label className="block space-y-2 text-sm">
                      <span className="text-muted-foreground">状态</span>
                      <select
                        value={projectForm.status}
                        onChange={(event) => setProjectForm((current) => ({ ...current, status: event.target.value }))}
                        className="h-10 w-full rounded-xl border border-input bg-background px-3 text-sm"
                      >
                        <option value="active">active</option>
                        <option value="paused">paused</option>
                        <option value="done">done</option>
                      </select>
                    </label>
                    <Textarea
                      value={projectForm.description}
                      onChange={(event) => setProjectForm((current) => ({ ...current, description: event.target.value }))}
                      placeholder="项目目标、范围、约束。"
                      className="min-h-[96px] rounded-xl"
                    />
                    <Textarea
                      value={projectForm.checkCommands}
                      onChange={(event) => setProjectForm((current) => ({ ...current, checkCommands: event.target.value }))}
                      placeholder="每行一个检查命令，例如 npm test / npm run lint"
                      className="min-h-[120px] rounded-xl font-mono text-xs"
                    />
                    <div className="flex gap-2">
                      <Button className="flex-1 rounded-xl" onClick={() => void handleSaveProject()} disabled={isMutating}>
                        <Save className="mr-2 h-4 w-4" />
                        保存项目设置
                      </Button>
                      <Button variant="outline" className="rounded-xl" onClick={() => void loadProject(selectedProject.id, fileTreePath)} disabled={isMutating}>
                        <RefreshCcw className="mr-2 h-4 w-4" />
                        刷新
                      </Button>
                    </div>
                    <Button variant="outline" className="w-full rounded-xl" onClick={() => void handleArchiveProject()} disabled={isMutating}>
                      <Archive className="mr-2 h-4 w-4" />
                      归档项目
                    </Button>
                  </div>
                </section>

                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">Resources</div>
                      <div className="mt-1 text-xs text-muted-foreground">自动上下文之外，你手动钉住的重要文件、链接、说明。</div>
                    </div>
                    <Badge variant="secondary">{allResources.length}</Badge>
                  </div>
                  <div className="mt-4 space-y-3">
                    <div className="grid gap-3 grid-cols-[110px_minmax(0,1fr)]">
                      <select
                        value={resourceForm.type}
                        onChange={(event) => setResourceForm((current) => ({ ...current, type: event.target.value }))}
                        className="h-10 rounded-xl border border-input bg-background px-3 text-sm"
                      >
                        <option value="note">note</option>
                        <option value="url">url</option>
                        <option value="file">file</option>
                        <option value="repo-path">repo-path</option>
                        <option value="doc">doc</option>
                      </select>
                      <Input value={resourceForm.title} onChange={(event) => setResourceForm((current) => ({ ...current, title: event.target.value }))} placeholder="资源标题（可选）" />
                    </div>
                    <Textarea value={resourceForm.uri} onChange={(event) => setResourceForm((current) => ({ ...current, uri: event.target.value }))} placeholder="URL、文件路径或说明内容" className="min-h-[96px] rounded-xl" />
                    <label className="flex items-center gap-2 text-sm text-muted-foreground">
                      <input type="checkbox" checked={resourceForm.pinned} onChange={(event) => setResourceForm((current) => ({ ...current, pinned: event.target.checked }))} />
                      直接钉住到项目上下文
                    </label>
                    <Button className="w-full rounded-xl" onClick={() => void handleAddResource()} disabled={isMutating || !resourceForm.uri.trim()}>
                      <Pin className="mr-2 h-4 w-4" />
                      添加资源
                    </Button>
                  </div>
                  <div className="mt-4 space-y-2">
                    {allResources.map((resource) => (
                      <div key={resource.id} className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <div className="truncate text-sm font-medium">{resource.title || resource.type}</div>
                              {resource.pinned ? <Badge variant="secondary">Pinned</Badge> : null}
                              <Badge variant="outline">{resource.type}</Badge>
                            </div>
                            <div className="mt-2 break-all text-xs text-muted-foreground">{resource.uri}</div>
                          </div>
                          <Button size="sm" variant="outline" onClick={() => void handleDeleteResource(resource.id)}>
                            <Trash2 className="mr-1 h-3.5 w-3.5" />
                            删除
                          </Button>
                        </div>
                      </div>
                    ))}
                    {!allResources.length && <div className="text-xs text-muted-foreground">还没有资源。</div>}
                  </div>
                </section>

                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">File Tree</div>
                      <div className="mt-1 text-xs text-muted-foreground">项目 repoPath 对应的文件上下文浏览器。</div>
                    </div>
                    {isFilesLoading ? (
                      <Badge variant="secondary">加载中</Badge>
                    ) : (
                      <Badge variant="secondary">
                        {(fileTree?.filteredEntries ?? fileTree?.entries.length) || 0}
                        {typeof fileTree?.totalEntries === 'number' && (fileTree.filteredEntries ?? fileTree.entries.length) !== fileTree.totalEntries ? ` / ${fileTree.totalEntries}` : ''}
                      </Badge>
                    )}
                  </div>
                  {!selectedProject.repoPath ? (
                    <div className="mt-4 rounded-2xl border border-dashed border-border/60 px-3 py-5 text-xs text-muted-foreground">
                      先给项目配置 repoPath，文件树就会在这里展示。
                    </div>
                  ) : (
                    <>
                      <div className="mt-4 rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                        <div className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">Repo Root</div>
                        <div className="mt-2 break-all text-xs text-muted-foreground">{selectedProject.repoPath}</div>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void loadProjectFiles(selectedProject.id, fileTree?.parentPath || '')}
                            disabled={!fileTree?.parentPath && fileTree?.parentPath !== ''}
                          >
                            <Undo2 className="mr-1 h-3.5 w-3.5" />
                            上一级
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => void loadProjectFiles(selectedProject.id, fileTreePath)} disabled={isFilesLoading}>
                            <RefreshCcw className="mr-1 h-3.5 w-3.5" />
                            刷新
                          </Button>
                        </div>
                        <div className="mt-3 grid gap-2 lg:grid-cols-[minmax(0,1fr)_120px_auto_auto]">
                          <Input
                            value={fileTreeQuery}
                            onChange={(event) => setFileTreeQuery(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') void loadProjectFiles(selectedProject.id, fileTreePath);
                            }}
                            placeholder="搜索当前目录中的文件/文件夹"
                          />
                          <select
                            value={fileTreeEntryType}
                            onChange={(event) => setFileTreeEntryType(event.target.value)}
                            className="h-10 rounded-xl border border-input bg-background px-3 text-sm"
                          >
                            <option value="all">全部</option>
                            <option value="dir">目录</option>
                            <option value="file">文件</option>
                          </select>
                          <label className="flex items-center gap-2 rounded-xl border border-border/60 px-3 text-sm text-muted-foreground">
                            <input
                              type="checkbox"
                              checked={fileTreeIncludeHidden}
                              onChange={(event) => setFileTreeIncludeHidden(event.target.checked)}
                            />
                            隐藏项
                          </label>
                          <div className="flex gap-2">
                            <Button size="sm" variant="outline" onClick={() => void loadProjectFiles(selectedProject.id, fileTreePath)} disabled={isFilesLoading}>
                              <Search className="mr-1 h-3.5 w-3.5" />
                              筛选
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => {
                                setFileTreeQuery('');
                                setFileTreeEntryType('all');
                                setFileTreeIncludeHidden(false);
                                void loadProjectFiles(selectedProject.id, fileTreePath, { query: '', entryType: 'all', includeHidden: false });
                              }}
                              disabled={isFilesLoading}
                            >
                              清空
                            </Button>
                          </div>
                        </div>
                      </div>

                      <div className="mt-4 rounded-2xl border border-border/60 bg-background/70">
                        <div className="border-b border-border/60 px-3 py-2 text-xs text-muted-foreground">
                          当前路径：/{fileTree?.currentPath || ''}
                          {fileTree?.query ? ` · 过滤：${fileTree.query}` : ''}
                          {fileTree?.entryType ? ` · 类型：${fileTree.entryType}` : ''}
                        </div>
                        <div className="divide-y divide-border/50">
                          {fileTree?.entries.map((entry) => (
                            <div key={entry.path || entry.name} className="flex items-center justify-between gap-2 px-3 py-2">
                              <button
                                type="button"
                                onClick={() => entry.type === 'dir' ? void loadProjectFiles(selectedProject.id, entry.path) : undefined}
                                className={`flex min-w-0 flex-1 items-center gap-2 text-left ${entry.type === 'dir' ? 'hover:text-primary' : ''}`}
                              >
                                {entry.type === 'dir' ? <Folder className="h-4 w-4 shrink-0 text-primary" /> : <File className="h-4 w-4 shrink-0 text-muted-foreground" />}
                                <div className="min-w-0 flex-1">
                                  <div className="truncate text-sm">{entry.name}</div>
                                  <div className="truncate text-[11px] text-muted-foreground">{entry.path}</div>
                                </div>
                                {entry.type === 'dir' ? <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" /> : null}
                              </button>
                              <div className="flex shrink-0 items-center gap-2">
                                <Badge variant="outline">{entry.type}</Badge>
                                <Button size="sm" variant="outline" onClick={() => void handlePinRepoEntry(entry.path, entry.name)} disabled={isMutating}>
                                  <Pin className="mr-1 h-3.5 w-3.5" />
                                  钉住
                                </Button>
                              </div>
                            </div>
                          ))}
                          {!fileTree?.entries.length && (
                            <div className="px-3 py-5 text-xs text-muted-foreground">当前目录下没有匹配的文件或目录。</div>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                </section>
              </div>
            )}
          </TabsContent>

          <TabsContent value="memory" className="mt-4 flex-1 overflow-y-auto">
            {!selectedProject ? (
              <PanelEmpty icon={<Brain className="h-5 w-5" />} title="还没有项目上下文" description="先选中一个项目，记忆面板就会展示偏好、决策和 learnings。" />
            ) : (
              <div className="space-y-5 pr-1">
                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="text-sm font-medium">Memory Search</div>
                      <div className="mt-1 text-xs text-muted-foreground">跨偏好、决策、项目 learnings 搜索</div>
                    </div>
                    {isMemoryLoading ? <Badge variant="secondary">加载中</Badge> : null}
                  </div>
                  <div className="mt-4 flex gap-2">
                    <Input value={memoryQuery} onChange={(event) => setMemoryQuery(event.target.value)} placeholder="例如 race / pnpm / Zustand" />
                    <Button variant="outline" onClick={() => void loadMemory(selectedProject.id, memoryQuery)}>
                      <Search className="h-4 w-4" />
                    </Button>
                    <Button variant="outline" onClick={() => { setMemoryQuery(''); void loadMemory(selectedProject.id, ''); }}>
                      <RefreshCcw className="h-4 w-4" />
                    </Button>
                  </div>
                </section>

                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium">Preferences</div>
                    <Badge variant="secondary">{preferences.length}</Badge>
                  </div>
                  <div className="mt-4 grid gap-2">
                    <div className="grid grid-cols-3 gap-2">
                      <Input value={preferenceForm.category} onChange={(event) => setPreferenceForm((current) => ({ ...current, category: event.target.value }))} placeholder="category" />
                      <Input value={preferenceForm.key} onChange={(event) => setPreferenceForm((current) => ({ ...current, key: event.target.value }))} placeholder="key" />
                      <Input value={preferenceForm.value} onChange={(event) => setPreferenceForm((current) => ({ ...current, value: event.target.value }))} placeholder="value" />
                    </div>
                    <Button className="rounded-xl" onClick={() => void handleCreatePreference()} disabled={isMutating}>
                      <Plus className="mr-2 h-4 w-4" />
                      新增偏好
                    </Button>
                  </div>
                  <div className="mt-4 space-y-2">
                    {preferences.map((preference) => (
                      <div key={preference.id} className="rounded-2xl border border-border/60 bg-background/70 p-3">
                        <div className="flex items-center justify-between gap-2">
                          <div>
                            <div className="text-sm font-medium">{preference.key}</div>
                            <div className="text-xs text-muted-foreground">{preference.category} · {fmtTime(preference.createdAt)}</div>
                          </div>
                          <Button size="sm" variant="outline" onClick={() => void handleSavePreference(preference.id)}>
                            <Save className="mr-1 h-3.5 w-3.5" />
                            保存
                          </Button>
                        </div>
                        <Input
                          className="mt-3"
                          value={preferenceDrafts[preference.id] ?? preference.value}
                          onChange={(event) => setPreferenceDrafts((current) => ({ ...current, [preference.id]: event.target.value }))}
                        />
                      </div>
                    ))}
                    {!preferences.length && <div className="text-xs text-muted-foreground">还没有记录偏好。</div>}
                  </div>
                </section>

                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium">Decision Log</div>
                    <Badge variant="secondary">{decisions.length}</Badge>
                  </div>
                  <div className="mt-4 space-y-2">
                    <Input value={decisionForm.question} onChange={(event) => setDecisionForm((current) => ({ ...current, question: event.target.value }))} placeholder="决策问题" />
                    <Input value={decisionForm.decision} onChange={(event) => setDecisionForm((current) => ({ ...current, decision: event.target.value }))} placeholder="最终决策" />
                    <Textarea value={decisionForm.reasoning} onChange={(event) => setDecisionForm((current) => ({ ...current, reasoning: event.target.value }))} placeholder="为什么这么选" className="min-h-[84px] rounded-xl" />
                    <Button className="w-full rounded-xl" onClick={() => void handleCreateDecision()} disabled={isMutating || !selectedProjectId}>
                      <Plus className="mr-2 h-4 w-4" />
                      记录决策
                    </Button>
                  </div>
                  <div className="mt-4 space-y-2">
                    {decisions.map((decision) => (
                      <div key={decision.id} className="rounded-2xl border border-border/60 bg-background/70 p-3">
                        <div className="grid gap-2">
                          <Input
                            value={decisionDrafts[decision.id]?.question ?? decision.question}
                            onChange={(event) => setDecisionDrafts((current) => ({
                              ...current,
                              [decision.id]: {
                                question: event.target.value,
                                decision: current[decision.id]?.decision ?? decision.decision,
                                reasoning: current[decision.id]?.reasoning ?? decision.reasoning,
                              },
                            }))}
                            placeholder="决策问题"
                          />
                          <Input
                            value={decisionDrafts[decision.id]?.decision ?? decision.decision}
                            onChange={(event) => setDecisionDrafts((current) => ({
                              ...current,
                              [decision.id]: {
                                question: current[decision.id]?.question ?? decision.question,
                                decision: event.target.value,
                                reasoning: current[decision.id]?.reasoning ?? decision.reasoning,
                              },
                            }))}
                            placeholder="最终决策"
                          />
                          <Textarea
                            value={decisionDrafts[decision.id]?.reasoning ?? decision.reasoning}
                            onChange={(event) => setDecisionDrafts((current) => ({
                              ...current,
                              [decision.id]: {
                                question: current[decision.id]?.question ?? decision.question,
                                decision: current[decision.id]?.decision ?? decision.decision,
                                reasoning: event.target.value,
                              },
                            }))}
                            placeholder="为什么这么选"
                            className="min-h-[84px] rounded-xl"
                          />
                        </div>
                        <div className="mt-3 flex items-center justify-between gap-2">
                          <div className="text-[11px] text-muted-foreground">{fmtTime(decision.createdAt)}</div>
                          <Button size="sm" variant="outline" onClick={() => void handleSaveDecision(decision.id)} disabled={isMutating}>
                            <Save className="mr-1 h-3.5 w-3.5" />
                            保存
                          </Button>
                        </div>
                      </div>
                    ))}
                    {!decisions.length && <div className="text-xs text-muted-foreground">还没有决策记录。</div>}
                  </div>
                </section>

                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium">Project Learnings</div>
                    <Badge variant="secondary">{learnings.length}</Badge>
                  </div>
                  <div className="mt-4 space-y-2">
                    <Textarea value={learningForm.content} onChange={(event) => setLearningForm({ content: event.target.value })} placeholder="例如：OAuth token refresh 要处理 race condition。" className="min-h-[96px] rounded-xl" />
                    <Button className="w-full rounded-xl" onClick={() => void handleCreateLearning()} disabled={isMutating || !selectedProjectId}>
                      <Plus className="mr-2 h-4 w-4" />
                      新增 learning
                    </Button>
                  </div>
                  <div className="mt-4 space-y-2">
                    {learnings.map((learning) => (
                      <div key={learning.id} className="rounded-2xl border border-border/60 bg-background/70 p-3">
                        <Textarea
                          value={learningDrafts[learning.id] ?? learning.content}
                          onChange={(event) => setLearningDrafts((current) => ({ ...current, [learning.id]: event.target.value }))}
                          className="min-h-[96px] rounded-xl"
                        />
                        <div className="mt-3 flex items-center justify-between gap-2">
                          <div className="text-[11px] text-muted-foreground">{fmtTime(learning.createdAt)}</div>
                          <Button size="sm" variant="outline" onClick={() => void handleSaveLearning(learning.id)} disabled={isMutating}>
                            <Save className="mr-1 h-3.5 w-3.5" />
                            保存
                          </Button>
                        </div>
                      </div>
                    ))}
                    {!learnings.length && <div className="text-xs text-muted-foreground">还没有项目 learnings。</div>}
                  </div>
                </section>
              </div>
            )}
          </TabsContent>

          <TabsContent value="detail" className="mt-4 flex-1 overflow-y-auto">
            <div className="space-y-4 pr-1">
              <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium">Recent Runs</div>
                    <div className="mt-1 text-xs text-muted-foreground">点击任意 Run 查看完整 artifacts</div>
                  </div>
                  <Badge variant="secondary">{activeRuns.length}</Badge>
                </div>
                <div className="mt-4 space-y-2">
                  {activeRuns.map((run) => (
                    <RunInlineCard
                      key={run.id}
                      run={run}
                      compact
                      selected={selectedRunId === run.id}
                      onSelect={() => setSelectedRunId(run.id)}
                      onAdopt={() => void handleAdoptRun(run.id)}
                      onCancel={() => void handleCancelRun(run.id)}
                      onRetry={() => void handleRetryRun(run.id)}
                    />
                  ))}
                  {!activeRuns.length && <div className="text-xs text-muted-foreground">当前 Thread 还没有 Run。</div>}
                </div>
              </section>

              {!selectedRunDetail ? (
                <PanelEmpty icon={<FileText className="h-5 w-5" />} title="还没有选中 Run" description="从上面的 Run 列表或消息流里点一个，即可查看详细 artifacts。" />
              ) : (
                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="text-sm font-medium">{asString(selectedRunDetail.metadata?.compareLabel) || selectedRunDetail.agent}</div>
                        <Badge variant={runTone(selectedRunDetail.status) as never}>{selectedRunDetail.status}</Badge>
                        {selectedRunDetail.metadata?.adopted ? <Badge variant="secondary">Adopted</Badge> : null}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {selectedRunDetail.model || '未指定模型'} · {selectedRunDetail.reasoningEffort || 'default'} · round {selectedRunDetail.round}/{selectedRunDetail.maxRounds}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">{fmtTime(selectedRunDetail.createdAt)}</div>
                    </div>
                    {isRunLoading ? <Badge variant="secondary">加载中</Badge> : null}
                  </div>

                  <div className="mt-4 rounded-2xl border border-border/60 bg-background/70 px-3 py-3 text-xs text-muted-foreground">
                    <div className="font-medium text-foreground">命令</div>
                    <div className="mt-2 break-all font-mono">{commandLine(selectedRunDetail)}</div>
                  </div>

                  <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Current Round</div>
                      <div className="mt-2 text-sm font-medium text-foreground">第 {selectedDetailRoundGroup?.round || selectedRunDetail.round} 轮 / 共 {selectedRunDetail.maxRounds} 轮</div>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Duration</div>
                      <div className="mt-2 text-sm font-medium text-foreground">{fmtDuration(selectedRunDetail.durationMs)}</div>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Artifacts</div>
                      <div className="mt-2 text-sm font-medium text-foreground">{selectedRunDetail.artifacts?.length || 0} 条</div>
                    </div>
                    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Work Dir</div>
                      <div className="mt-2 break-all font-mono text-[11px] text-foreground">{selectedRunDetail.workDir || '未记录'}</div>
                    </div>
                  </div>

                  {detailRounds.length ? (
                    <div className="mt-4 rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <div className="text-sm font-medium">Rounds</div>
                      <div className="mt-1 text-xs text-muted-foreground">按轮查看 summary / checks / feedback / patch。</div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {detailRounds.map((item) => (
                          <button
                            key={item.round}
                            type="button"
                            onClick={() => setDetailRound(item.round)}
                            className={`rounded-full border px-3 py-1 text-xs transition ${
                              detailRound === item.round ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/60 bg-background/80'
                            }`}
                          >
                            Round {item.round}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    {artifactIndex.summary ? (
                      <button
                        type="button"
                        onClick={() => setDetailArtifactType('summary')}
                        className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40"
                      >
                        <div className="text-sm font-medium">Summary</div>
                        <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">{artifactPreview(artifactIndex.summary.content, 360)}</div>
                      </button>
                    ) : null}
                    {artifactIndex.feedback ? (
                      <button
                        type="button"
                        onClick={() => setDetailArtifactType('feedback')}
                        className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40"
                      >
                        <div className="text-sm font-medium">Retry Feedback</div>
                        <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">{artifactPreview(artifactIndex.feedback.content, 360)}</div>
                      </button>
                    ) : null}
                    {artifactIndex.changes ? (
                      <button
                        type="button"
                        onClick={() => setDetailArtifactType('changes')}
                        className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40"
                      >
                        <div className="text-sm font-medium">Changes</div>
                        <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">{artifactPreview(artifactIndex.changes.content, 360)}</div>
                      </button>
                    ) : null}
                    {artifactIndex.patch ? (
                      <button
                        type="button"
                        onClick={() => setDetailArtifactType('patch')}
                        className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40"
                      >
                        <div className="text-sm font-medium">Patch</div>
                        <div className="mt-2 whitespace-pre-wrap text-xs leading-6 text-muted-foreground">{artifactPreview(artifactIndex.patch.content, 480)}</div>
                      </button>
                    ) : null}
                  </div>

                  {selectedCheckResults.length ? (
                    <div className="mt-4 rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                      <div className="text-sm font-medium">Checks</div>
                      <div className="mt-1 text-xs text-muted-foreground">第 {selectedDetailRoundGroup?.round || selectedRunDetail.round} 轮验收结果</div>
                      <div className="mt-3 space-y-2">
                        {selectedCheckResults.map((item, index) => (
                          <div key={`${item.command || 'check'}-${index}`} className="rounded-xl border border-border/50 bg-background/80 px-3 py-2 text-xs">
                            <div className="flex items-center justify-between gap-2">
                              <div className="break-all font-mono">{asString(item.command) || `check-${index + 1}`}</div>
                              <Badge variant={item.passed ? 'default' : 'destructive'}>{item.passed ? 'passed' : 'failed'}</Badge>
                            </div>
                            {checkOutputText(item) ? <div className="mt-2 whitespace-pre-wrap text-muted-foreground">{checkOutputText(item)}</div> : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <div className="mt-4 flex flex-wrap gap-2">
                    {artifactTypes.map((type) => (
                      <button
                        key={type}
                        type="button"
                        onClick={() => setDetailArtifactType(type)}
                        className={`rounded-full border px-3 py-1 text-xs transition ${
                          detailArtifactType === type ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/60 bg-background/70'
                        }`}
                      >
                        {type}
                      </button>
                    ))}
                  </div>

                  <div className="mt-4 rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <div className="text-sm font-medium">{selectedArtifact?.title || detailArtifactType}</div>
                      <div className="text-xs text-muted-foreground">Round {selectedDetailRoundGroup?.round || selectedRunDetail.round}</div>
                    </div>
                    {selectedArtifact ? (
                      <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words text-xs leading-6 text-muted-foreground">
                        {selectedArtifact.content || '（空）'}
                      </pre>
                    ) : (
                      <div className="text-xs text-muted-foreground">当前 Round 没有这个 artifact。</div>
                    )}
                  </div>
                </section>
              )}
            </div>
          </TabsContent>

          <TabsContent value="compare" className="mt-4 flex-1 overflow-y-auto">
            {!selectedThread ? (
              <PanelEmpty icon={<GitCompareArrows className="h-5 w-5" />} title="还没有线程" description="先选中一个 Thread，再发起多 Agent 对比。" />
            ) : (
              <div className="space-y-4 pr-1">
                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium">Run Compare</div>
                      <div className="mt-1 text-xs text-muted-foreground">并发跑多个 Agent / 命令，对比摘要、状态与 artifacts。</div>
                    </div>
                    <Badge variant="secondary">{compareGroups.length} Sessions</Badge>
                  </div>
                  <div className="mt-4 space-y-3">
                    <Textarea
                      value={comparePrompt}
                      onChange={(event) => setComparePrompt(event.target.value)}
                      placeholder="例如：分别实现 refresh token 流程，并给出对比。留空时会使用左侧输入框内容。"
                      className="min-h-[96px] rounded-xl"
                    />
                    <div className="grid gap-2 rounded-2xl border border-border/60 bg-background/70 p-3 text-sm">
                      <label className="flex items-center gap-2 text-muted-foreground">
                        <input type="checkbox" checked={compareAgents.codex} onChange={(event) => setCompareAgents((current) => ({ ...current, codex: event.target.checked }))} />
                        Codex (`gpt-5.4` / `xhigh`)
                      </label>
                      <label className="flex items-center gap-2 text-muted-foreground">
                        <input type="checkbox" checked={compareAgents.claude} onChange={(event) => setCompareAgents((current) => ({ ...current, claude: event.target.checked }))} />
                        Claude Code
                      </label>
                      <label className="flex items-center gap-2 text-muted-foreground">
                        <input type="checkbox" checked={compareAgents.custom} onChange={(event) => setCompareAgents((current) => ({ ...current, custom: event.target.checked }))} />
                        Custom Command
                      </label>
                    </div>
                    {compareAgents.custom ? (
                      <div className="space-y-2">
                        <Input value={compareCustomLabel} onChange={(event) => setCompareCustomLabel(event.target.value)} placeholder="自定义方案名称" />
                        <Textarea value={compareCustomCommand} onChange={(event) => setCompareCustomCommand(event.target.value)} placeholder="例如：pytest -q 或 bash -lc 'npm test'" className="min-h-[96px] rounded-xl font-mono text-xs" />
                      </div>
                    ) : null}
                    <Button className="w-full rounded-xl" onClick={() => void handleRunCompare()} disabled={isMutating}>
                      <GitCompareArrows className="mr-2 h-4 w-4" />
                      发起并发对比
                    </Button>
                  </div>
                </section>

                <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                  <div className="text-sm font-medium">Compare Sessions</div>
                  <div className="mt-3 space-y-2">
                    {compareGroups.map((group) => (
                      <button
                        key={group.compareId}
                        type="button"
                        onClick={() => setSelectedCompareId(group.compareId)}
                        className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                          selectedCompareId === group.compareId ? 'border-primary/50 bg-primary/8' : 'border-border/60 bg-background/70'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <div className="truncate text-sm font-medium">{group.prompt}</div>
                          <Badge variant="secondary">{group.runs.length} runs</Badge>
                        </div>
                        <div className="mt-2 text-xs text-muted-foreground">{fmtTime(group.createdAt)}</div>
                      </button>
                    ))}
                    {!compareGroups.length && <div className="text-xs text-muted-foreground">还没有 compare session。</div>}
                  </div>
                </section>

                {selectedCompareGroup ? (
                  <section className="rounded-2xl border border-border/60 bg-background/60 p-4">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium">当前对比</div>
                        <div className="mt-1 text-xs text-muted-foreground">{selectedCompareGroup.prompt}</div>
                      </div>
                      <Badge variant="secondary">{selectedCompareGroup.runs.length} 路</Badge>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {compareArtifactTypes.map((type) => (
                        <button
                          key={type}
                          type="button"
                          onClick={() => setCompareArtifactType(type)}
                          className={`rounded-full border px-3 py-1 text-xs transition ${
                            compareArtifactType === type ? 'border-primary/50 bg-primary/10 text-primary' : 'border-border/60 bg-background/70'
                          }`}
                        >
                          {type}
                        </button>
                      ))}
                    </div>
                    <div className="mt-4 flex gap-3 overflow-x-auto pb-1">
                      {selectedCompareGroup.runs.map((run) => {
                        const detailRun = compareRunDetails[run.id] || run;
                        const compareIndex = buildArtifactIndex(detailRun.artifacts);
                        const checks = parseCheckResults(compareIndex.check_result?.content);
                        const compareArtifact = compareIndex[compareArtifactType];
                        const preview = compareArtifactType === 'summary'
                          ? compareArtifact?.content || summaryText(detailRun)
                          : compareArtifact?.content || '';
                        return (
                          <div key={run.id} className="min-w-[320px] shrink-0 rounded-2xl border border-border/60 bg-background/70 p-3 xl:min-w-[360px]">
                            <div className="flex items-start justify-between gap-3">
                              <div>
                                <div className="flex items-center gap-2">
                                  <div className="text-sm font-medium">{asString(run.metadata?.compareLabel) || run.agent}</div>
                                  <Badge variant={runTone(run.status) as never}>{run.status}</Badge>
                                  {detailRun.metadata?.adopted ? <Badge variant="secondary">Adopted</Badge> : null}
                                </div>
                                <div className="mt-1 text-xs text-muted-foreground">
                                  {detailRun.model || '未指定模型'} · {detailRun.reasoningEffort || 'default'} · {fmtTime(detailRun.createdAt)}
                                </div>
                              </div>
                              <Button size="sm" variant="outline" onClick={() => { setSelectedRunId(run.id); setActivePanel('detail'); }}>
                                查看详情
                              </Button>
                            </div>
                            <div className="mt-3 grid gap-2 sm:grid-cols-3">
                              <div className="rounded-xl border border-border/50 bg-background/80 px-3 py-2 text-xs">
                                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Round</div>
                                <div className="mt-1 font-medium text-foreground">{detailRun.round}/{detailRun.maxRounds}</div>
                              </div>
                              <div className="rounded-xl border border-border/50 bg-background/80 px-3 py-2 text-xs">
                                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Duration</div>
                                <div className="mt-1 font-medium text-foreground">{fmtDuration(detailRun.durationMs)}</div>
                              </div>
                              <div className="rounded-xl border border-border/50 bg-background/80 px-3 py-2 text-xs">
                                <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Artifacts</div>
                                <div className="mt-1 font-medium text-foreground">{detailRun.artifacts?.length || 0}</div>
                              </div>
                            </div>
                            {compareArtifactType === 'check_result' ? (
                              checks.length ? (
                                <div className="mt-3 space-y-2">
                                  {checks.map((item, index) => (
                                    <div key={`${run.id}-${index}`} className="rounded-xl border border-border/50 bg-background/80 px-3 py-2 text-xs">
                                      <div className="flex items-center justify-between gap-2">
                                        <div className="break-all font-mono">{asString(item.command) || `check-${index + 1}`}</div>
                                        <Badge variant={item.passed ? 'default' : 'destructive'}>{item.passed ? 'passed' : 'failed'}</Badge>
                                      </div>
                                      {checkOutputText(item) ? <div className="mt-2 whitespace-pre-wrap text-muted-foreground">{checkOutputText(item)}</div> : null}
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <div className="mt-3 rounded-xl border border-border/50 bg-background/80 px-3 py-3 text-xs text-muted-foreground">这个方案还没有 check 结果。</div>
                              )
                            ) : (
                              <div className="mt-3 rounded-xl border border-border/50 bg-background/80 px-3 py-3">
                                <div className="text-xs font-medium text-foreground">{compareArtifact?.title || compareArtifactType}</div>
                                <pre className="mt-2 max-h-[260px] overflow-auto whitespace-pre-wrap break-words text-xs leading-6 text-muted-foreground">{artifactPreview(preview, compareArtifactType === 'patch' ? 1200 : 520)}</pre>
                              </div>
                            )}
                            <div className="mt-3 flex flex-wrap gap-2">
                              <Button size="sm" variant="outline" onClick={() => { setSelectedRunId(run.id); setActivePanel('detail'); }}>
                                查看详情
                              </Button>
                              <Button size="sm" variant="outline" onClick={() => void handleAdoptRun(run.id)}>
                                采纳方案
                              </Button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                ) : null}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </aside>
    </div>
  );
}

function PanelEmpty({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-[1.75rem] border border-dashed border-border/60 bg-background/40 px-5 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary/10 text-primary">{icon}</div>
      <div className="text-sm font-medium">{title}</div>
      <div className="max-w-xs text-xs leading-6 text-muted-foreground">{description}</div>
    </div>
  );
}

function RunInlineCard({
  run,
  onAdopt,
  onCancel,
  onRetry,
  onSelect,
  compact = false,
  selected = false,
}: {
  run: ConversationRun;
  onAdopt: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onSelect: () => void;
  compact?: boolean;
  selected?: boolean;
}) {
  const compareLabel = asString(run.metadata?.compareLabel);
  const adopted = Boolean(run.metadata?.adopted);

  return (
    <div className={`rounded-2xl border px-3 py-3 ${selected ? 'border-primary/50 bg-primary/8' : 'border-border/60 bg-background/70'}`}>
      <div className="flex items-start justify-between gap-3">
        <button type="button" onClick={onSelect} className="min-w-0 flex-1 text-left">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-sm font-medium">{compareLabel || run.agent}</div>
            <Badge variant={runTone(run.status) as never}>{run.status}</Badge>
            {adopted ? <Badge variant="secondary">Adopted</Badge> : null}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {run.model || '未指定模型'} · {run.reasoningEffort || 'default'} · round {run.round}/{run.maxRounds}
          </div>
          {!compact ? (
            <div className="mt-2 text-xs text-muted-foreground">
              {commandLine(run)}
            </div>
          ) : null}
        </button>
        <div className="flex shrink-0 items-center gap-2">
          {['pending', 'running', 'checking'].includes(run.status) ? (
            <Button size="sm" variant="outline" onClick={onCancel}>
              <Square className="mr-1 h-3.5 w-3.5" />
              取消
            </Button>
          ) : null}
          {['failed', 'cancelled'].includes(run.status) ? (
            <Button size="sm" variant="outline" onClick={onRetry}>
              <RefreshCcw className="mr-1 h-3.5 w-3.5" />
              重试
            </Button>
          ) : null}
          <Button size="sm" variant="outline" onClick={onAdopt}>
            采纳
          </Button>
        </div>
      </div>
    </div>
  );
}
