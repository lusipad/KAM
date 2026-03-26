import { useEffect, useMemo, useState } from 'react';

import { SettingsPanel } from '@/components/Settings/SettingsPanel';
import { collectRunChangeFiles } from '@/components/V2/RunChangePreview';
import { ContextPanel } from '@/features/context/ContextPanel';
import { MemoryView } from '@/features/memory/MemoryView';
import {
  ProjectCreateModal,
  type ProjectCreateForm,
} from '@/features/projects/ProjectCreateModal';
import { RunDetailDrawer } from '@/features/runs/RunDetailDrawer';
import { ThreadView, type AgentOption } from '@/features/threads/ThreadView';
import { AppShell } from '@/layout/AppShell';
import { Sidebar } from '@/layout/Sidebar';
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

type WorkspaceMode = 'workspace' | 'memory';

const WORKSPACE_STORAGE_KEY = 'kam.v2.workspace';
const NEW_PROJECT_FORM: ProjectCreateForm = {
  title: '',
  description: '',
  repoPath: '',
  checkCommands: '',
};

const ARTIFACT_TYPE_PRIORITY = [
  'summary',
  'check_result',
  'feedback',
  'changes',
  'patch',
  'stdout',
  'stderr',
  'prompt',
  'context',
];

function readStoredWorkspaceState(): {
  selectedProjectId?: string | null;
  selectedThreadId?: string | null;
  workspaceMode?: WorkspaceMode;
} {
  if (typeof window === 'undefined') return {};

  try {
    const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
    if (!raw) return {};

    const parsed = JSON.parse(raw) as {
      selectedProjectId?: string | null;
      selectedThreadId?: string | null;
      workspaceMode?: WorkspaceMode;
    };

    return {
      selectedProjectId: typeof parsed.selectedProjectId === 'string' ? parsed.selectedProjectId : null,
      selectedThreadId: typeof parsed.selectedThreadId === 'string' ? parsed.selectedThreadId : null,
      workspaceMode: parsed.workspaceMode === 'memory' ? 'memory' : 'workspace',
    };
  } catch {
    return {};
  }
}

function getErrorMessage(error: unknown) {
  return error instanceof Error && error.message ? error.message : '请求失败，请稍后再试。';
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

function upsertProjectSummary(current: ProjectRecord[], nextProject: ProjectRecord) {
  if (current.some((item) => item.id === nextProject.id)) {
    return current.map((item) => (item.id === nextProject.id ? { ...item, ...nextProject } : item));
  }
  return [nextProject, ...current];
}

function upsertThreadSummary(current: ProjectThread[], nextThread: ProjectThread) {
  if (current.some((item) => item.id === nextThread.id)) {
    return current.map((item) => (item.id === nextThread.id ? { ...item, ...nextThread } : item));
  }
  return [nextThread, ...current];
}

function upsertThreadMessage(thread: ProjectThread | null, message: ThreadMessageRecord) {
  if (!thread || thread.id !== message.threadId) return thread;

  const existingMessages = thread.messages || [];
  const index = existingMessages.findIndex((item) => item.id === message.id);
  const nextMessages = [...existingMessages];

  if (index >= 0) {
    nextMessages[index] = {
      ...nextMessages[index],
      ...message,
      runs: message.runs || nextMessages[index].runs,
    };
  } else {
    nextMessages.push(message);
  }

  nextMessages.sort((left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime());

  return {
    ...thread,
    messages: nextMessages,
    messageCount: Math.max(thread.messageCount || 0, nextMessages.length),
    updatedAt: message.createdAt,
  };
}

function isBootstrapResponse(
  value: PostThreadMessageResponse | BootstrapThreadMessageResponse,
): value is BootstrapThreadMessageResponse {
  return isRecord(value) && isRecord(value.project) && isRecord(value.thread);
}

function splitCommands(value: string) {
  return value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean);
}

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
    grouped.get(round)?.push(artifact);
  }

  return Array.from(grouped.entries())
    .sort((left, right) => right[0] - left[0])
    .map(([round, items]) => ({
      round,
      artifacts: items,
      index: buildArtifactIndex(items),
    }));
}

function parseCheckResults(content?: string) {
  try {
    const parsed = JSON.parse(content || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function collectThreadRuns(thread: ProjectThread | null) {
  const runs = new Map<string, ConversationRun>();
  (thread?.runs || []).forEach((run) => {
    runs.set(run.id, run);
  });
  (thread?.messages || []).forEach((message) => {
    (message.runs || []).forEach((run) => {
      const existing = runs.get(run.id);
      runs.set(run.id, existing ? { ...existing, ...run } : run);
    });
  });
  return Array.from(runs.values());
}

export function WorkspaceView() {
  const storedState = readStoredWorkspaceState();
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(storedState.workspaceMode ?? 'workspace');
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(storedState.selectedProjectId ?? null);
  const [selectedProject, setSelectedProject] = useState<ProjectRecord | null>(null);
  const [threads, setThreads] = useState<ProjectThread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(storedState.selectedThreadId ?? null);
  const [selectedThread, setSelectedThread] = useState<ProjectThread | null>(null);

  const [agent, setAgent] = useState<AgentOption>('codex');
  const [customCommand, setCustomCommand] = useState('');
  const [messageText, setMessageText] = useState('');
  const [streamingReplyText, setStreamingReplyText] = useState('');

  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [createProjectForm, setCreateProjectForm] = useState<ProjectCreateForm>(NEW_PROJECT_FORM);
  const [contextOpen, setContextOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showProjectEditor, setShowProjectEditor] = useState(false);
  const [showResourceComposer, setShowResourceComposer] = useState(false);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [runDetailOpen, setRunDetailOpen] = useState(false);
  const [runDetailsById, setRunDetailsById] = useState<Record<string, ConversationRun>>({});
  const [detailRound, setDetailRound] = useState<number | null>(null);
  const [detailArtifactType, setDetailArtifactType] = useState('summary');
  const [detailChangePath, setDetailChangePath] = useState<string | null>(null);

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

  const [fileTreePath, setFileTreePath] = useState('');
  const [fileTree, setFileTree] = useState<ProjectFileTreeRecord | null>(null);
  const [fileTreeQuery, setFileTreeQuery] = useState('');

  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);
  const [isMemoryLoading, setIsMemoryLoading] = useState(false);
  const [isFilesLoading, setIsFilesLoading] = useState(false);
  const [isRunLoading, setIsRunLoading] = useState(false);
  const [isSendingMessage, setIsSendingMessage] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const pinnedResources = useMemo(
    () => selectedProject?.pinnedResources || selectedProject?.resources?.filter((item) => item.pinned) || [],
    [selectedProject],
  );

  const threadRuns = useMemo(() => collectThreadRuns(selectedThread), [selectedThread]);
  const activeRuns = useMemo(() => threadRuns.filter((run) => isActiveRun(run)), [threadRuns]);
  const runIdsInThread = useMemo(() => threadRuns.map((run) => run.id), [threadRuns]);
  const runWatchKey = useMemo(
    () => threadRuns.map((run) => `${run.id}:${run.status}:${run.round}`).join('|'),
    [threadRuns],
  );
  const activeThreadRunKey = useMemo(
    () => threadRuns.filter((run) => isActiveRun(run)).map((run) => `${run.id}:${run.status}:${run.round}`).join('|'),
    [threadRuns],
  );

  const selectedRunDetail = useMemo(() => {
    if (!selectedRunId) return null;
    return runDetailsById[selectedRunId] || threadRuns.find((run) => run.id === selectedRunId) || null;
  }, [selectedRunId, runDetailsById, threadRuns]);

  const detailRounds = useMemo(() => buildArtifactRounds(selectedRunDetail?.artifacts), [selectedRunDetail]);
  const selectedDetailRoundGroup = useMemo(
    () => detailRounds.find((item) => item.round === detailRound) || detailRounds[0] || null,
    [detailRound, detailRounds],
  );
  const detailArtifactIndex = useMemo(
    () => buildArtifactIndex(selectedDetailRoundGroup?.artifacts),
    [selectedDetailRoundGroup],
  );
  const detailArtifactTypes = useMemo(
    () => sortArtifactTypes(Object.keys(detailArtifactIndex)),
    [detailArtifactIndex],
  );
  const selectedArtifact = detailArtifactIndex[detailArtifactType];
  const selectedCheckResults = useMemo(
    () => parseCheckResults(detailArtifactIndex.check_result?.content) as Record<string, unknown>[],
    [detailArtifactIndex],
  );

  useEffect(() => {
    void loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setSelectedProject(null);
      setThreads([]);
      setSelectedThreadId(null);
      setSelectedThread(null);
      setFileTree(null);
      setFileTreePath('');
      return;
    }

    void loadProject(selectedProjectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedThreadId) {
      setSelectedThread(null);
      return;
    }

    void loadThread(selectedThreadId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedThreadId]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(
      WORKSPACE_STORAGE_KEY,
      JSON.stringify({
        selectedProjectId,
        selectedThreadId,
        workspaceMode,
      }),
    );
  }, [selectedProjectId, selectedThreadId, workspaceMode]);

  useEffect(() => {
    if (!selectedThreadId) return;

    const eventSource = new EventSource(getV2ThreadEventsUrl(selectedThreadId));
    const handleThreadEvent = (rawEvent: Event) => {
      const event = rawEvent as MessageEvent<string>;

      try {
        const payload = JSON.parse(event.data) as unknown;
        const hasActiveRuns = applyThreadSnapshotPayload(payload);
        if (hasActiveRuns === false) {
          eventSource.close();
        }
      } catch {
        eventSource.close();
      }
    };

    ['snapshot', 'thread-updated', 'run-progress', 'thread-done'].forEach((eventName) => {
      eventSource.addEventListener(eventName, handleThreadEvent as EventListener);
    });
    eventSource.onerror = () => {
      eventSource.close();
    };

    return () => {
      ['snapshot', 'thread-updated', 'run-progress', 'thread-done'].forEach((eventName) => {
        eventSource.removeEventListener(eventName, handleThreadEvent as EventListener);
      });
      eventSource.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedThreadId, activeThreadRunKey]);

  useEffect(() => {
    if (!selectedProject) {
      setProjectForm({
        title: '',
        description: '',
        repoPath: '',
        status: 'active',
        checkCommands: '',
      });
      setShowProjectEditor(false);
      setShowResourceComposer(false);
      return;
    }

    setProjectForm({
      title: selectedProject.title || '',
      description: selectedProject.description || '',
      repoPath: selectedProject.repoPath || '',
      status: selectedProject.status || 'active',
      checkCommands: (selectedProject.checkCommands || []).join('\n'),
    });
    setShowProjectEditor(false);
    setShowResourceComposer(false);
  }, [selectedProject]);

  useEffect(() => {
    setRunDetailsById({});
    setSelectedRunId(null);
    setRunDetailOpen(false);
  }, [selectedThread?.id]);

  useEffect(() => {
    if (!selectedThread?.id || !runIdsInThread.length) return;

    let cancelled = false;
    const eventSources: EventSource[] = [];

    Promise.all(
      runIdsInThread.map(async (runId) => {
        try {
          return await v2RunsApi.getById(runId);
        } catch {
          return null;
        }
      }),
    ).then((results) => {
      if (cancelled) return;
      setRunDetailsById((current) => {
        const next = { ...current };
        results.forEach((result) => {
          if (result) next[result.id] = result;
        });
        return next;
      });
    });

    threadRuns.forEach((run) => {
      if (!isActiveRun(run)) return;

      const eventSource = new EventSource(getV2RunEventsUrl(run.id, 60_000));
      eventSource.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as {
            run?: ConversationRun;
            artifacts?: ThreadRunArtifactRecord[];
          };
          if (!payload.run) return;
          setRunDetailsById((current) => ({
            ...current,
            [payload.run!.id]: {
              ...payload.run!,
              artifacts: payload.artifacts || [],
            },
          }));
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
      eventSources.push(eventSource);
    });

    return () => {
      cancelled = true;
      eventSources.forEach((source) => source.close());
    };
  }, [selectedThread?.id, runIdsInThread, runWatchKey, threadRuns]);

  useEffect(() => {
    if (workspaceMode !== 'memory') return;
    const handle = window.setTimeout(() => {
      void loadMemory(selectedProjectId, memoryQuery);
    }, 180);
    return () => window.clearTimeout(handle);
  }, [workspaceMode, selectedProjectId, memoryQuery]);

  useEffect(() => {
    if (!contextOpen || !selectedProject?.repoPath || !selectedProjectId || fileTree) return;
    void loadProjectFiles(selectedProjectId, fileTreePath || '');
  }, [contextOpen, fileTree, fileTreePath, selectedProject?.repoPath, selectedProjectId]);

  useEffect(() => {
    if (!contextOpen || !selectedProject?.repoPath || !selectedProjectId) return;
    const handle = window.setTimeout(() => {
      void loadProjectFiles(selectedProjectId, fileTreePath, { query: fileTreeQuery });
    }, 220);
    return () => window.clearTimeout(handle);
  }, [contextOpen, selectedProject?.repoPath, selectedProjectId, fileTreePath, fileTreeQuery]);

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
    if (!detailArtifactTypes.length) {
      setDetailArtifactType('summary');
      return;
    }
    if (!detailArtifactTypes.includes(detailArtifactType)) {
      setDetailArtifactType(detailArtifactTypes[0]);
    }
  }, [detailArtifactType, detailArtifactTypes]);

  useEffect(() => {
    setDetailChangePath(null);
  }, [selectedRunId, detailRound]);

  useEffect(() => {
    const files = collectRunChangeFiles(detailArtifactIndex.changes, detailArtifactIndex.patch);
    if (!files.length) {
      setDetailChangePath(null);
      return;
    }
    if (detailChangePath && files.some((item) => item.path === detailChangePath)) return;
    setDetailChangePath(files[0].path);
  }, [detailArtifactIndex, detailChangePath]);

  function mergeRunsIntoCache(runs: ConversationRun[]) {
    if (!runs.length) return;
    setRunDetailsById((current) => {
      const next = { ...current };
      runs.forEach((run) => {
        next[run.id] = current[run.id] ? { ...current[run.id], ...run } : run;
      });
      return next;
    });
  }

  function syncThreadState(nextThread: ProjectThread) {
    setSelectedThread(nextThread);
    setThreads((current) => upsertThreadSummary(current, nextThread));
    mergeRunsIntoCache(collectThreadRuns(nextThread));
  }

  function applyThreadSnapshotPayload(payload: unknown) {
    if (!isRecord(payload)) return null;

    const streamThread = payload.thread;
    if (isRecord(streamThread) && typeof streamThread.id === 'string') {
      syncThreadState(streamThread as unknown as ProjectThread);
    }

    if (typeof payload.hasActiveRuns === 'boolean') {
      return payload.hasActiveRuns;
    }

    return null;
  }

  async function loadProjects() {
    setIsLoading(true);
    try {
      setErrorMessage(null);
      const response = await v2ProjectsApi.list();
      const nextProjects = response.projects || [];
      setProjects(nextProjects);
      const nextProjectId =
        selectedProjectId && nextProjects.some((item) => item.id === selectedProjectId)
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
      setProjects((current) => upsertProjectSummary(current, project));

      const nextThreads = project.threads || [];
      setThreads(nextThreads);
      const nextThreadId =
        selectedThreadId && nextThreads.some((item) => item.id === selectedThreadId)
          ? selectedThreadId
          : nextThreads[0]?.id || null;
      setSelectedThreadId(nextThreadId);
      setSelectedThread((current) => (current?.id === nextThreadId ? current : null));

      if (project.repoPath && contextOpen) {
        await loadProjectFiles(project.id, nextFilePath ?? fileTreePath);
      } else if (!project.repoPath) {
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
      syncThreadState(thread);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function loadMemory(projectId: string | null, query: string) {
    setIsMemoryLoading(true);
    try {
      setErrorMessage(null);
      if (query.trim()) {
        const response = await v2MemoryApi.search({
          query: query.trim(),
          project_id: projectId || undefined,
        });
        setPreferences(response.preferences || []);
        setDecisions(response.decisions || []);
        setLearnings(response.learnings || []);
        setPreferenceDrafts(Object.fromEntries((response.preferences || []).map((item) => [item.id, item.value])));
        setDecisionDrafts(
          Object.fromEntries(
            (response.decisions || []).map((item) => [
              item.id,
              { question: item.question, decision: item.decision, reasoning: item.reasoning || '' },
            ]),
          ),
        );
        setLearningDrafts(Object.fromEntries((response.learnings || []).map((item) => [item.id, item.content])));
        return;
      }

      const [preferencesResponse, decisionsResponse, learningsResponse] = await Promise.all([
        v2MemoryApi.listPreferences(),
        v2MemoryApi.listDecisions({ project_id: projectId || undefined }),
        v2MemoryApi.listLearnings({ project_id: projectId || undefined }),
      ]);

      setPreferences(preferencesResponse.preferences || []);
      setDecisions(decisionsResponse.decisions || []);
      setLearnings(learningsResponse.learnings || []);
      setPreferenceDrafts(Object.fromEntries((preferencesResponse.preferences || []).map((item) => [item.id, item.value])));
      setDecisionDrafts(
        Object.fromEntries(
          (decisionsResponse.decisions || []).map((item) => [
            item.id,
            { question: item.question, decision: item.decision, reasoning: item.reasoning || '' },
          ]),
        ),
      );
      setLearningDrafts(Object.fromEntries((learningsResponse.learnings || []).map((item) => [item.id, item.content])));
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMemoryLoading(false);
    }
  }

  async function loadProjectFiles(projectId: string, path = '', options?: { query?: string }) {
    setIsFilesLoading(true);
    try {
      setErrorMessage(null);
      const tree = await v2ProjectsApi.listFiles(projectId, {
        path,
        query: options?.query?.trim() || undefined,
      });
      setFileTree(tree);
      setFileTreePath(tree.currentPath || '');
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
      setFileTree(null);
      setFileTreePath('');
    } finally {
      setIsFilesLoading(false);
    }
  }

  async function loadRunDetail(runId: string) {
    setIsRunLoading(true);
    try {
      setErrorMessage(null);
      const run = await v2RunsApi.getById(runId);
      setRunDetailsById((current) => ({
        ...current,
        [run.id]: run,
      }));
      return run;
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
      return null;
    } finally {
      setIsRunLoading(false);
    }
  }

  async function openRunDetail(runId: string, artifactType = 'summary') {
    setSelectedRunId(runId);
    setDetailArtifactType(artifactType);
    setRunDetailOpen(true);
    if (!runDetailsById[runId]?.artifacts?.length) {
      await loadRunDetail(runId);
    }
  }

  function applyThreadMessageStreamEvent(event: ThreadMessageStreamEvent) {
    if (!isRecord(event.data)) return;
    const payload = event.data;

    if (event.event === 'assistant-reply-delta') {
      const content = asString(payload.content) || asString(payload.delta);
      if (content) setStreamingReplyText(content);
      return;
    }

    if (event.event === 'assistant-reply-complete') {
      const reply = asThreadMessage(payload.reply);
      if (reply) {
        setSelectedThread((current) => upsertThreadMessage(current, reply));
      }
      setStreamingReplyText('');
      return;
    }

    const message = asThreadMessage(payload.message);
    if (message) {
      setSelectedThread((current) => upsertThreadMessage(current, message));
    }

    const reply = asThreadMessage(payload.reply);
    if (reply) {
      setSelectedThread((current) => upsertThreadMessage(current, reply));
    }

    const streamThread = payload.thread;
    if (isRecord(streamThread) && typeof streamThread.id === 'string') {
      syncThreadState(streamThread as unknown as ProjectThread);
    }

    mergeRunsIntoCache(asRunList(payload.runs));
  }

  async function handleCreateProject() {
    if (!createProjectForm.title.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      const created = await v2ProjectsApi.create({
        title: createProjectForm.title.trim(),
        description: createProjectForm.description.trim(),
        repoPath: createProjectForm.repoPath.trim() || undefined,
        checkCommands: splitCommands(createProjectForm.checkCommands),
      });
      setCreateProjectForm(NEW_PROJECT_FORM);
      setCreateProjectOpen(false);
      setWorkspaceMode('workspace');
      setSelectedProjectId(created.id);
      setSelectedThreadId(null);
      setProjects((current) => upsertProjectSummary(current, created));
      await loadProject(created.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSendMessage() {
    const draftMessage = messageText.trim();
    if (!draftMessage) return;

    setWorkspaceMode('workspace');
    setIsMutating(true);
    setIsSendingMessage(true);
    setErrorMessage(null);
    setStreamingReplyText('');
    setMessageText('');

    try {
      const command = agent === 'custom' ? customCommand.trim() || undefined : undefined;
      const model = agent === 'codex' ? 'gpt-5.4' : undefined;
      const reasoningEffort = agent === 'codex' ? 'xhigh' : undefined;

      let nextProjectId = selectedProjectId;
      let nextThreadId = selectedThreadId;
      let response: PostThreadMessageResponse | BootstrapThreadMessageResponse;

      if (!selectedProjectId) {
        const bootstrapResponse = await v2ThreadsApi.bootstrapMessage({
          content: draftMessage,
          createRun: true,
          agent,
          command,
          model,
          reasoningEffort,
        });
        response = bootstrapResponse;
        nextProjectId = bootstrapResponse.project.id;
        nextThreadId = bootstrapResponse.thread.id;
        setSelectedProjectId(nextProjectId);
        setSelectedThreadId(nextThreadId);
      } else {
        if (!selectedThreadId) {
          const createdThread = await v2ThreadsApi.create(selectedProjectId, {
            title: '新对话',
          });
          nextThreadId = createdThread.id;
          setSelectedThreadId(nextThreadId);
          syncThreadState(createdThread);
        }

        const streamedResponse = await v2ThreadsApi.postMessageStream(
          nextThreadId as string,
          {
            content: draftMessage,
            createRun: true,
            agent,
            command,
            model,
            reasoningEffort,
          },
          {
            onEvent: applyThreadMessageStreamEvent,
          },
        );

        response =
          streamedResponse ||
          (await v2ThreadsApi.postMessage(nextThreadId as string, {
            content: draftMessage,
            createRun: true,
            agent,
            command,
            model,
            reasoningEffort,
          }));
      }

      if (agent === 'custom') setCustomCommand('');

      mergeRunsIntoCache(response.runs || []);

      if (response.thread) {
        syncThreadState(response.thread);
      } else if (nextThreadId) {
        await loadThread(nextThreadId);
      }

      if (isBootstrapResponse(response)) {
        setSelectedProject(response.project);
        setProjects((current) => upsertProjectSummary(current, response.project));
        setThreads(response.project.threads || [response.thread]);
      } else if (nextProjectId) {
        await loadProject(nextProjectId, fileTreePath);
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
      setShowProjectEditor(false);
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
      setContextOpen(false);
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
      setResourceForm({
        type: 'note',
        title: '',
        uri: '',
        pinned: true,
      });
      setShowResourceComposer(false);
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
      const fullPath = `${selectedProject.repoPath.replace(/[\\/]+$/, '')}/${relativePath}`;
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
      await loadMemory(selectedProjectId, memoryQuery);
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
      await loadMemory(selectedProjectId, memoryQuery);
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
      await loadMemory(selectedProjectId, memoryQuery);
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
      const response = await v2RunsApi.adopt(runId);
      setRunDetailsById((current) => ({
        ...current,
        [response.id]: response,
      }));
      if (selectedThreadId) {
        await loadThread(selectedThreadId);
      }
      if (selectedProjectId) {
        await loadProject(selectedProjectId, fileTreePath);
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
      const response = await v2RunsApi.cancel(runId);
      setRunDetailsById((current) => ({
        ...current,
        [response.id]: response,
      }));
      if (selectedThreadId) {
        await loadThread(selectedThreadId);
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
      setRunDetailsById((current) => ({
        ...current,
        [response.id]: response,
      }));
      if (selectedThreadId) {
        await loadThread(selectedThreadId);
      }
      await openRunDetail(response.id, 'summary');
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  return (
    <>
      <AppShell
        sidebar={
          <Sidebar
            projects={projects}
            selectedProjectId={selectedProjectId}
            selectedProject={selectedProject}
            threads={threads}
            selectedThreadId={selectedThreadId}
            workspaceMode={workspaceMode}
            isLoading={isLoading}
            onSelectProject={(projectId) => {
              setWorkspaceMode('workspace');
              setSelectedProjectId(projectId);
            }}
            onSelectThread={(threadId) => {
              setWorkspaceMode('workspace');
              setSelectedThreadId(threadId);
              setSelectedThread((current) => (current?.id === threadId ? current : null));
            }}
            onCreateProject={() => setCreateProjectOpen(true)}
            onOpenMemory={() => setWorkspaceMode('memory')}
            onOpenSettings={() => setSettingsOpen(true)}
            onOpenWorkspace={() => setWorkspaceMode('workspace')}
          />
        }
      >
        <section className="lite-panel flex h-full min-h-0 min-w-0 flex-col rounded-[1.9rem]">
          {workspaceMode === 'memory' ? (
            <MemoryView
              selectedProject={selectedProject}
              selectedProjectId={selectedProjectId}
              memoryQuery={memoryQuery}
              onMemoryQueryChange={setMemoryQuery}
              onBack={() => setWorkspaceMode('workspace')}
              preferences={preferences}
              decisions={decisions}
              learnings={learnings}
              preferenceForm={preferenceForm}
              decisionForm={decisionForm}
              learningForm={learningForm}
              preferenceDrafts={preferenceDrafts}
              decisionDrafts={decisionDrafts}
              learningDrafts={learningDrafts}
              onPreferenceFormChange={setPreferenceForm}
              onDecisionFormChange={setDecisionForm}
              onLearningFormChange={setLearningForm}
              onPreferenceDraftChange={(id, value) => setPreferenceDrafts((current) => ({ ...current, [id]: value }))}
              onDecisionDraftChange={(id, next) => setDecisionDrafts((current) => ({ ...current, [id]: next }))}
              onLearningDraftChange={(id, value) => setLearningDrafts((current) => ({ ...current, [id]: value }))}
              onCreatePreference={() => void handleCreatePreference()}
              onCreateDecision={() => void handleCreateDecision()}
              onCreateLearning={() => void handleCreateLearning()}
              onSavePreference={(id) => void handleSavePreference(id)}
              onSaveDecision={(id) => void handleSaveDecision(id)}
              onSaveLearning={(id) => void handleSaveLearning(id)}
              isLoading={isMemoryLoading}
            />
          ) : (
            <ThreadView
              selectedProject={selectedProject}
              selectedThread={selectedThread}
              messageText={messageText}
              onMessageTextChange={setMessageText}
              agent={agent}
              onAgentChange={setAgent}
              customCommand={customCommand}
              onCustomCommandChange={setCustomCommand}
              isMutating={isMutating}
              isSendingMessage={isSendingMessage}
              streamingReplyText={streamingReplyText}
              errorMessage={errorMessage}
              onSendMessage={() => void handleSendMessage()}
              onOpenContext={() => setContextOpen(true)}
              onOpenRunDetail={(runId, artifactType) => void openRunDetail(runId, artifactType)}
              onAdoptRun={(runId) => void handleAdoptRun(runId)}
              onCancelRun={(runId) => void handleCancelRun(runId)}
              onRetryRun={(runId) => void handleRetryRun(runId)}
              runDetailsById={runDetailsById}
            />
          )}
        </section>
      </AppShell>

      <ContextPanel
        open={contextOpen}
        onOpenChange={setContextOpen}
        selectedProject={selectedProject}
        projectForm={projectForm}
        onProjectFormChange={setProjectForm}
        showProjectEditor={showProjectEditor}
        onProjectEditorToggle={setShowProjectEditor}
        pinnedResources={pinnedResources}
        resourceForm={resourceForm}
        onResourceFormChange={setResourceForm}
        showResourceComposer={showResourceComposer}
        onResourceComposerToggle={setShowResourceComposer}
        activeRuns={activeRuns}
        fileTree={fileTree}
        fileTreeQuery={fileTreeQuery}
        onFileTreeQueryChange={setFileTreeQuery}
        isFilesLoading={isFilesLoading}
        onRefreshFiles={() => {
          if (!selectedProjectId) return;
          void loadProjectFiles(selectedProjectId, fileTreePath, { query: fileTreeQuery });
        }}
        onOpenRun={(runId, artifactType) => void openRunDetail(runId, artifactType)}
        onSaveProject={() => void handleSaveProject()}
        onArchiveProject={() => void handleArchiveProject()}
        onAddResource={() => void handleAddResource()}
        onDeleteResource={(resourceId) => void handleDeleteResource(resourceId)}
        onLoadPath={(path) => {
          if (!selectedProjectId) return;
          void loadProjectFiles(selectedProjectId, path, { query: fileTreeQuery });
        }}
        onPinRepoEntry={(path, name) => void handlePinRepoEntry(path, name)}
      />

      <RunDetailDrawer
        open={runDetailOpen}
        onOpenChange={setRunDetailOpen}
        run={selectedRunDetail}
        isLoading={isRunLoading}
        detailRounds={detailRounds}
        detailRound={detailRound}
        onDetailRoundChange={setDetailRound}
        detailArtifactTypes={detailArtifactTypes}
        detailArtifactType={detailArtifactType}
        onDetailArtifactTypeChange={setDetailArtifactType}
        detailArtifactIndex={detailArtifactIndex}
        selectedArtifact={selectedArtifact}
        selectedCheckResults={selectedCheckResults}
        detailChangePath={detailChangePath}
        onDetailChangePath={setDetailChangePath}
        onAdoptRun={(runId) => void handleAdoptRun(runId)}
        onCancelRun={(runId) => void handleCancelRun(runId)}
        onRetryRun={(runId) => void handleRetryRun(runId)}
      />

      <ProjectCreateModal
        open={createProjectOpen}
        onOpenChange={setCreateProjectOpen}
        form={createProjectForm}
        onFormChange={setCreateProjectForm}
        onSubmit={() => void handleCreateProject()}
        isMutating={isMutating}
      />

      <SettingsPanel isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </>
  );
}
