import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Bot,
  ChevronDown,
  ChevronUp,
  FolderInput,
  GitCompareArrows,
  LoaderCircle,
  Play,
  Plus,
  RefreshCcw,
  Sparkles,
  Square,
  Trash2,
  WandSparkles,
} from 'lucide-react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { tasksApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { AgentRunRecord, ComparisonRow, ReviewData, RunArtifactView, WorkspaceTask } from '@/types';

type RunType = 'codex' | 'claude-code' | 'custom';
type BadgeVariant = 'default' | 'secondary' | 'outline' | 'destructive';
type WorkspacePanel = 'overview' | 'sources' | 'runs' | 'review';
type NextActionIntent = 'add-ref' | 'resolve-context' | 'dispatch' | 'monitor-runs' | 'review';

interface NextAction {
  label: string;
  description: string;
  panel: WorkspacePanel;
  intent: NextActionIntent;
  cta: string;
}

const taskMeta = {
  inbox: ['收件箱', 'secondary'],
  ready: ['可执行', 'default'],
  running: ['执行中', 'default'],
  review: ['待收口', 'secondary'],
  done: ['完成', 'outline'],
  archived: ['归档', 'outline'],
} as const;

const runMeta = {
  planned: ['待启动', 'secondary'],
  queued: ['排队中', 'secondary'],
  running: ['运行中', 'default'],
  completed: ['已完成', 'outline'],
  failed: ['失败', 'destructive'],
  canceled: ['已取消', 'outline'],
} as const satisfies Record<string, readonly [string, BadgeVariant]>;

const priorityMeta = {
  low: '低优先',
  medium: '中优先',
  high: '高优先',
} as const satisfies Record<WorkspaceTask['priority'], string>;

const runPresets: Record<RunType, string> = {
  codex: 'Codex',
  'claude-code': 'Claude Code',
  custom: 'Custom Command',
};

const panelMeta = {
  overview: { label: '概览', hint: '只看当前阶段与下一步。' },
  sources: { label: '资料', hint: '引用与 Context 按需展开。' },
  runs: { label: '执行', hint: 'Run 队列和产物只在这里出现。' },
  review: { label: '收口', hint: 'Review 与 Compare 回到任务维度。' },
} as const satisfies Record<WorkspacePanel, { label: string; hint: string }>;

const liveArtifactTypes = ['stdout', 'stderr', 'summary', 'changes', 'patch'] as const;

const artifactOrder: Record<string, number> = {
  summary: 1,
  changes: 2,
  patch: 3,
  stdout: 4,
  stderr: 5,
  context: 6,
  plan: 7,
  prompt: 8,
};

function fmt(value?: string | Date | null) {
  if (!value) return '刚刚';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? '刚刚'
    : new Intl.DateTimeFormat('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(date);
}

function getErrorMessage(error: unknown) {
  return error instanceof Error && error.message ? error.message : '请求失败，请稍后重试。';
}

function getPreview(content: string, limit: number) {
  const normalized = content.trim();
  if (!normalized) return { text: '', truncated: false };
  if (normalized.length <= limit) return { text: normalized, truncated: false };
  return { text: `${normalized.slice(0, limit).trimEnd()}...`, truncated: true };
}

function getRecommendedPanel(task: WorkspaceTask): WorkspacePanel {
  if (!task.refs?.length || !task.latestSnapshot) return 'sources';
  if (task.runs?.some((run) => ['planned', 'queued', 'running'].includes(run.status))) return 'runs';
  if (!task.runs?.length) return 'runs';
  return 'overview';
}

function getNextAction(task: WorkspaceTask): NextAction {
  if (!task.refs?.length) {
    return {
      label: '先补引用',
      description: '让任务先有边界和入口，再生成上下文。',
      panel: 'sources',
      intent: 'add-ref',
      cta: '添加引用',
    };
  }
  if (!task.latestSnapshot) {
    return {
      label: '生成 Context',
      description: '把任务卡、引用和已有信息收敛成可派发的上下文。',
      panel: 'sources',
      intent: 'resolve-context',
      cta: '生成 Context',
    };
  }
  if (!task.runs?.length) {
    return {
      label: '派发 Agent',
      description: '上下文已经就绪，现在进入执行阶段。',
      panel: 'runs',
      intent: 'dispatch',
      cta: '创建 Run',
    };
  }
  if (task.runs.some((run) => ['planned', 'queued', 'running'].includes(run.status))) {
    return {
      label: '盯运行态',
      description: '当前有活跃 run，先看状态和关键产物。',
      panel: 'runs',
      intent: 'monitor-runs',
      cta: '查看 Runs',
    };
  }
  return {
    label: '进入收口',
    description: '运行已结束，把输出收回到任务层完成比较与 review。',
    panel: 'review',
    intent: 'review',
    cta: '查看收口',
  };
}

function getRunRank(status: AgentRunRecord['status']) {
  switch (status) {
    case 'running':
      return 0;
    case 'queued':
      return 1;
    case 'planned':
      return 2;
    case 'failed':
      return 3;
    case 'completed':
      return 4;
    case 'canceled':
      return 5;
    default:
      return 9;
  }
}

function sortRuns(runs: AgentRunRecord[]) {
  return [...runs].sort((a, b) => {
    const rankDiff = getRunRank(a.status) - getRunRank(b.status);
    if (rankDiff !== 0) return rankDiff;
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
  });
}

export function TasksView() {
  const initialLoadRef = useRef(false);
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [selectedTask, setSelectedTask] = useState<WorkspaceTask | null>(null);
  const [review, setReview] = useState<ReviewData | null>(null);
  const [comparison, setComparison] = useState<ComparisonRow[]>([]);
  const [selectedRunArtifacts, setSelectedRunArtifacts] = useState<RunArtifactView[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [artifactFilter, setArtifactFilter] = useState('all');
  const [activePanel, setActivePanel] = useState<WorkspacePanel>('overview');
  const [isLoading, setIsLoading] = useState(false);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isTaskComposerOpen, setIsTaskComposerOpen] = useState(true);
  const [isRefComposerOpen, setIsRefComposerOpen] = useState(false);
  const [isRunComposerOpen, setIsRunComposerOpen] = useState(false);
  const [isSnapshotExpanded, setIsSnapshotExpanded] = useState(false);
  const [isReviewExpanded, setIsReviewExpanded] = useState(false);
  const [taskForm, setTaskForm] = useState<{ title: string; description: string; priority: WorkspaceTask['priority'] }>({
    title: '',
    description: '',
    priority: 'medium',
  });
  const [refForm, setRefForm] = useState({ type: 'url', label: '', value: '' });
  const [runForm, setRunForm] = useState<{ name: string; type: RunType; command: string }>({
    name: 'Codex',
    type: 'codex',
    command: '',
  });

  const selectedRun = useMemo(
    () => selectedTask?.runs?.find((run) => run.id === selectedRunId) || null,
    [selectedTask, selectedRunId]
  );

  const sortedRuns = useMemo(() => sortRuns(selectedTask?.runs || []), [selectedTask?.runs]);

  const hasActiveRuns = useMemo(
    () => !!selectedTask?.runs?.some((run) => ['planned', 'queued', 'running'].includes(run.status)),
    [selectedTask]
  );

  const artifactFilters = useMemo(
    () => ['all', ...Array.from(new Set(selectedRunArtifacts.map((artifact) => artifact.type)))],
    [selectedRunArtifacts]
  );

  const filteredArtifacts = useMemo(
    () =>
      selectedRunArtifacts
        .filter((artifact) => artifactFilter === 'all' || artifact.type === artifactFilter)
        .sort((a, b) => (artifactOrder[a.type] || 99) - (artifactOrder[b.type] || 99)),
    [artifactFilter, selectedRunArtifacts]
  );

  const nextAction = useMemo(() => (selectedTask ? getNextAction(selectedTask) : null), [selectedTask]);
  const snapshotPreview = useMemo(
    () => getPreview(selectedTask?.latestSnapshot?.summary || '', 960),
    [selectedTask?.latestSnapshot?.summary]
  );
  const reviewPreview = useMemo(() => getPreview(review?.summary || '', 680), [review?.summary]);

  useEffect(() => {
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    void loadTasks();
    // Initial bootstrap intentionally runs once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedTask?.id || !hasActiveRuns) return;
    const timer = window.setInterval(() => void loadTaskDetail(selectedTask.id), 3000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTask?.id, hasActiveRuns]);

  const selectedRunStatus = selectedRun?.status;

  useEffect(() => {
    if (!selectedRunId || !selectedRunStatus || !['planned', 'queued', 'running'].includes(selectedRunStatus)) return;
    const eventSource = new EventSource(`/api/runs/${selectedRunId}/events?tail_chars=20000`);
    eventSource.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { run: AgentRunRecord; artifacts: RunArtifactView[] };
      setSelectedRunArtifacts(payload.artifacts || []);
      setSelectedTask((prev) =>
        prev && prev.id === payload.run.taskId
          ? {
              ...prev,
              runs: prev.runs?.map((run) => (run.id === payload.run.id ? { ...run, ...payload.run } : run)) || [],
            }
          : prev
      );
      if (['completed', 'failed', 'canceled'].includes(payload.run.status)) {
        eventSource.close();
        void loadTaskDetail(payload.run.taskId);
      }
    };
    eventSource.onerror = () => {
      eventSource.close();
      void loadRunArtifacts(selectedRunId, true);
    };
    return () => eventSource.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRunId, selectedRunStatus]);

  useEffect(() => {
    if (!selectedTask?.runs?.length) {
      setSelectedRunId(null);
      setSelectedRunArtifacts([]);
      return;
    }
    if (!selectedRunId || !selectedTask.runs.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(sortRuns(selectedTask.runs)[0]?.id || null);
    }
  }, [selectedTask?.runs, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || !selectedRun) return;
    void loadRunArtifacts(selectedRunId, ['planned', 'queued', 'running'].includes(selectedRun.status));
  }, [selectedRunId, selectedRun]);

  useEffect(() => {
    setArtifactFilter('all');
  }, [selectedRunId]);

  useEffect(() => {
    setIsSnapshotExpanded(false);
    setIsReviewExpanded(false);
    setIsRefComposerOpen(!(selectedTask?.refs?.length));
    setIsRunComposerOpen(!(selectedTask?.runs?.length));
  }, [selectedTask?.id, selectedTask?.refs?.length, selectedTask?.runs?.length]);

  return (
    <div className="space-y-4">
      {errorMessage && (
        <div className="lite-panel rounded-[1.5rem] border-destructive/20 bg-destructive/5 px-5 py-4 text-sm text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        {renderTaskPool()}
        {selectedTask ? renderWorkspace() : renderIdleWorkspace()}
      </div>
    </div>
  );

  async function loadTasks(selectedId?: string) {
    setIsLoading(true);
    try {
      setErrorMessage(null);
      const response = await tasksApi.getAll();
      const nextTasks = response.tasks || [];
      setTasks(nextTasks);
      setIsTaskComposerOpen(!nextTasks.length);
      const nextSelectedId = selectedId || selectedTask?.id || nextTasks[0]?.id;
      if (nextSelectedId) {
        await loadTaskDetail(nextSelectedId, { syncPanel: !selectedTask || nextSelectedId !== selectedTask.id });
      } else {
        setSelectedTask(null);
        setReview(null);
        setComparison([]);
        setSelectedRunId(null);
        setSelectedRunArtifacts([]);
        setActivePanel('overview');
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsLoading(false);
      setIsBootstrapping(false);
    }
  }

  async function loadTaskDetail(taskId: string, options?: { syncPanel?: boolean; clearComparison?: boolean }) {
    try {
      setErrorMessage(null);
      const [task, nextReview] = await Promise.all([tasksApi.getById(taskId), tasksApi.getReview(taskId)]);
      setSelectedTask(task);
      setReview(nextReview);
      if (options?.clearComparison || selectedTask?.id !== taskId) setComparison([]);
      if (options?.syncPanel) setActivePanel(getRecommendedPanel(task));
      return task;
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
      return null;
    }
  }

  async function loadRunArtifacts(runId: string, tail = false) {
    try {
      setErrorMessage(null);
      const response = await tasksApi.getRunArtifacts(runId, tail ? { tail_chars: 20000 } : undefined);
      setSelectedRunArtifacts(response.artifacts || []);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function act(fn: () => Promise<void>) {
    try {
      setErrorMessage(null);
      await fn();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function handleCreateTask() {
    if (!taskForm.title.trim()) return;
    const created = await tasksApi.create(taskForm);
    setTaskForm({ title: '', description: '', priority: 'medium' });
    setIsTaskComposerOpen(false);
    await loadTasks(created.id);
  }

  async function handleDeleteRef(refId: string) {
    if (!selectedTask) return;
    await tasksApi.deleteRef(selectedTask.id, refId);
    await loadTaskDetail(selectedTask.id);
  }

  async function handleSelectTask(taskId: string) {
    setSelectedRunId(null);
    setSelectedRunArtifacts([]);
    setArtifactFilter('all');
    await loadTaskDetail(taskId, { syncPanel: true, clearComparison: true });
  }

  async function handleResolveContext() {
    if (!selectedTask) return;
    setActivePanel('sources');
    await tasksApi.resolveContext(selectedTask.id);
    await loadTaskDetail(selectedTask.id);
  }

  async function handleQuickRuns() {
    if (!selectedTask) return;
    setActivePanel('runs');
    await tasksApi.createRuns(selectedTask.id, [
      { name: 'Codex', type: 'codex' },
      { name: 'Claude Code', type: 'claude-code' },
    ]);
    await loadTaskDetail(selectedTask.id);
  }

  async function handleCreateRun() {
    if (!selectedTask || !runForm.name.trim()) return;
    if (runForm.type === 'custom' && !runForm.command.trim()) return;
    setActivePanel('runs');
    await tasksApi.createRuns(selectedTask.id, [runForm]);
    setRunForm({ name: 'Codex', type: 'codex', command: '' });
    setIsRunComposerOpen(false);
    await loadTaskDetail(selectedTask.id);
  }

  async function handleStartRun(runId: string) {
    await tasksApi.startRun(runId);
    if (selectedTask) await loadTaskDetail(selectedTask.id);
  }

  async function handleCancelRun(runId: string) {
    await tasksApi.cancelRun(runId);
    if (selectedTask) await loadTaskDetail(selectedTask.id);
  }

  async function handleRetryRun(runId: string) {
    await tasksApi.retryRun(runId);
    if (selectedTask) await loadTaskDetail(selectedTask.id);
  }

  async function handleCompare() {
    if (!selectedTask) return;
    setActivePanel('review');
    const response = await tasksApi.compareReview(selectedTask.id);
    setComparison(response.comparison || []);
  }

  async function handleAddRef() {
    if (!selectedTask || !refForm.label.trim() || !refForm.value.trim()) return;
    setActivePanel('sources');
    await tasksApi.addRef(selectedTask.id, refForm);
    setRefForm({ type: 'url', label: '', value: '' });
    setIsRefComposerOpen(false);
    await loadTaskDetail(selectedTask.id);
  }

  async function handlePrimaryAction() {
    if (!selectedTask || !nextAction) return;

    switch (nextAction.intent) {
      case 'add-ref':
        setActivePanel('sources');
        setIsRefComposerOpen(true);
        break;
      case 'resolve-context':
        await act(handleResolveContext);
        break;
      case 'dispatch':
        setActivePanel('runs');
        setIsRunComposerOpen(true);
        break;
      case 'monitor-runs':
        setActivePanel('runs');
        break;
      case 'review':
        await act(handleCompare);
        break;
      default:
        break;
    }
  }

  function renderTaskPool() {
    return (
      <section className="lite-panel flex min-h-[calc(100dvh-3rem)] flex-col rounded-[2rem] p-4 lg:p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="lite-eyebrow">Inbox</div>
            <h2 className="font-display mt-2 text-2xl font-semibold">任务收件箱</h2>
            <p className="mt-2 text-sm text-muted-foreground">左侧只看任务列表和新建入口。</p>
          </div>
          <Button
            variant={isTaskComposerOpen ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => setIsTaskComposerOpen((prev) => !prev)}
            className="rounded-full"
          >
            <Plus className="h-4 w-4" />
            新建任务
          </Button>
        </div>

        {isTaskComposerOpen && (
          <div className="mt-5 rounded-[1.6rem] border border-border/80 bg-background/78 p-4">
            <div className="grid gap-3">
              <Input
                className="rounded-2xl border-border/80 bg-background/88"
                placeholder="任务标题"
                value={taskForm.title}
                onChange={(e) => setTaskForm((prev) => ({ ...prev, title: e.target.value }))}
              />
              <Textarea
                className="min-h-[100px] rounded-[1.35rem] border-border/80 bg-background/88"
                placeholder="任务描述 / 目标 / 约束"
                value={taskForm.description}
                onChange={(e) => setTaskForm((prev) => ({ ...prev, description: e.target.value }))}
              />
              <div className="flex flex-col gap-3 sm:flex-row">
                <select
                  value={taskForm.priority}
                  onChange={(e) =>
                    setTaskForm((prev) => ({ ...prev, priority: e.target.value as WorkspaceTask['priority'] }))
                  }
                  className="h-12 rounded-2xl border border-border/80 bg-background/88 px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="low">低优先级</option>
                  <option value="medium">中优先级</option>
                  <option value="high">高优先级</option>
                </select>
                <Button onClick={() => void act(handleCreateTask)} className="rounded-full sm:ml-auto">
                  创建任务
                </Button>
              </div>
            </div>
          </div>
        )}

        <div className="my-5 lite-soft-divider" />

        <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-[0.18em] text-muted-foreground">
          <span className="inline-flex items-center gap-2">
            任务列表
            {isLoading ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : null}
          </span>
          <span>{tasks.length} items</span>
        </div>

        <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {isBootstrapping &&
            Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="h-28 animate-pulse rounded-[1.6rem] border border-border/70 bg-background/60"
              />
            ))}

          {!isBootstrapping &&
            tasks.map((task) => {
              const itemNextAction = getNextAction(task);

              return (
                <button
                  key={task.id}
                  onClick={() => void handleSelectTask(task.id)}
                  className={cn(
                    'w-full rounded-[1.6rem] border p-4 text-left transition-all',
                    selectedTask?.id === task.id
                      ? 'border-primary/30 bg-primary/10 shadow-[0_18px_40px_rgba(202,99,49,0.12)]'
                      : 'border-border/80 bg-background/72 hover:-translate-y-0.5 hover:bg-background/88'
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-display line-clamp-2 text-lg font-semibold">{task.title}</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Badge variant={taskMeta[task.status][1]}>{taskMeta[task.status][0]}</Badge>
                        <Badge variant="outline">{priorityMeta[task.priority]}</Badge>
                      </div>
                    </div>
                    {selectedTask?.id === task.id && <ArrowRight className="mt-1 h-4 w-4 text-primary" />}
                  </div>
                  <p className="mt-3 line-clamp-2 text-sm leading-6 text-muted-foreground">
                    {task.description || '还没有补充描述。'}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <span>下一步</span>
                    <span>{itemNextAction.label}</span>
                    <span>·</span>
                    <span>{task.refs?.length || 0} refs</span>
                    <span>·</span>
                    <span>{task.runs?.length || 0} runs</span>
                    <span>·</span>
                    <span>{fmt(task.updatedAt)}</span>
                  </div>
                </button>
              );
            })}

          {!isBootstrapping && !tasks.length && (
            <div className="rounded-[1.7rem] border border-dashed border-border/80 bg-background/60 p-6 text-sm leading-7 text-muted-foreground">
              这里还没有任务。先把当前最重要的一件事接进来，再进入右侧工作台。
            </div>
          )}
        </div>
      </section>
    );
  }

  function renderIdleWorkspace() {
    return (
      <section className="lite-panel flex min-h-[calc(100dvh-3rem)] flex-col items-center justify-center rounded-[2rem] px-6 py-10 text-center">
        <div className="mx-auto max-w-[34rem]">
          <div className="lite-eyebrow">Workspace</div>
          <h1 className="font-display mt-3 text-4xl font-semibold leading-tight">右侧只服务当前任务，不再平铺所有信息。</h1>
          <p className="mt-4 text-sm leading-7 text-muted-foreground">
            从左侧选一个任务，右侧会按阶段只展示当前最相关的内容。引用、Context、Runs、收口都改成按需触发。
          </p>
          <div className="mt-6 inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/70 px-4 py-2 text-sm text-muted-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            先选任务，再进入工作台
          </div>
        </div>
      </section>
    );
  }

  function renderWorkspace() {
    if (!selectedTask || !nextAction) return renderIdleWorkspace();

    const readiness = [
      {
        label: '任务定焦',
        ready: !!selectedTask.title.trim(),
        detail: selectedTask.description ? '目标与约束已写入。' : '建议补一句描述，便于后续派发。',
      },
      {
        label: '引用封包',
        ready: !!selectedTask.refs?.length,
        detail: selectedTask.refs?.length ? `已封包 ${selectedTask.refs.length} 条引用。` : '还没有引用入口。',
      },
      {
        label: 'Context Snapshot',
        ready: !!selectedTask.latestSnapshot,
        detail: selectedTask.latestSnapshot
          ? `最近生成于 ${fmt(selectedTask.latestSnapshot.createdAt)}。`
          : '还没有生成上下文。',
      },
      {
        label: 'Agent Runs',
        ready: !!selectedTask.runs?.length,
        detail: selectedTask.runs?.length ? `已有 ${selectedTask.runs.length} 条执行线。` : '还没有派发 run。',
      },
      {
        label: 'Review / Compare',
        ready: !!review?.summary || !!comparison.length,
        detail: review?.summary || comparison.length ? '已经有收口信息。' : '等待 compare 与 review 汇总。',
      },
    ];

    return (
      <div className="space-y-4">
        <section className="lite-panel rounded-[2rem] p-5 lg:p-6">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-w-0">
              <div className="lite-eyebrow">Focused Task</div>
              <h1 className="font-display mt-3 text-3xl font-semibold leading-tight lg:text-4xl">{selectedTask.title}</h1>
              <p className="mt-4 max-w-[72ch] text-sm leading-7 text-muted-foreground">
                {selectedTask.description || '当前任务还没有补充描述。'}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge variant={taskMeta[selectedTask.status][1]}>{taskMeta[selectedTask.status][0]}</Badge>
                <Badge variant="outline">{priorityMeta[selectedTask.priority]}</Badge>
                <Badge variant="outline">{selectedTask.refs?.length || 0} refs</Badge>
                <Badge variant="outline">{selectedTask.runs?.length || 0} runs</Badge>
                <Badge variant="outline">更新于 {fmt(selectedTask.updatedAt)}</Badge>
              </div>
            </div>

            <div className="rounded-[1.6rem] border border-border/80 bg-background/78 p-4">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-muted-foreground">当前下一步</div>
              <div className="font-display mt-3 text-2xl font-semibold">{nextAction.label}</div>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">{nextAction.description}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button onClick={() => void handlePrimaryAction()} className="rounded-full px-5">
                  {nextAction.intent === 'resolve-context' && <WandSparkles className="h-4 w-4" />}
                  {nextAction.intent === 'dispatch' && <Bot className="h-4 w-4" />}
                  {nextAction.intent === 'review' && <GitCompareArrows className="h-4 w-4" />}
                  {nextAction.intent === 'add-ref' && <FolderInput className="h-4 w-4" />}
                  {nextAction.intent === 'monitor-runs' && <Sparkles className="h-4 w-4" />}
                  {nextAction.cta}
                </Button>
                {selectedTask.runs?.length ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setActivePanel('review');
                      void act(handleCompare);
                    }}
                    className="rounded-full px-5"
                  >
                    <GitCompareArrows className="h-4 w-4" />
                    Compare
                  </Button>
                ) : null}
              </div>
            </div>
          </div>
        </section>

        <Tabs value={activePanel} onValueChange={(value) => setActivePanel(value as WorkspacePanel)} className="space-y-4">
          <div className="overflow-x-auto">
            <TabsList className="h-auto min-w-full gap-2 rounded-[1.35rem] border border-border/80 bg-card/80 p-1.5 sm:min-w-0">
              {Object.entries(panelMeta).map(([value, item]) => (
                <TabsTrigger
                  key={value}
                  value={value}
                  className="min-w-[8rem] rounded-[1rem] px-4 py-3 data-[state=active]:border-border/70 data-[state=active]:bg-background"
                >
                  <span className="font-medium">{item.label}</span>
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          <TabsContent value="overview" className="space-y-4">
            <div className="grid gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
              <section className="lite-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="lite-eyebrow">Attention</div>
                    <h2 className="font-display mt-3 text-2xl font-semibold">{nextAction.label}</h2>
                    <p className="mt-3 text-sm leading-7 text-muted-foreground">{nextAction.description}</p>
                  </div>
                  <ArrowRight className="mt-1 h-5 w-5 text-muted-foreground" />
                </div>
                <div className="mt-5 rounded-[1.4rem] border border-border/80 bg-background/72 p-4">
                  <div className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">阶段提示</div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">{panelMeta[nextAction.panel].hint}</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button onClick={() => void handlePrimaryAction()} className="rounded-full">
                      {nextAction.cta}
                    </Button>
                    <Button variant="outline" onClick={() => setActivePanel(nextAction.panel)} className="rounded-full">
                      打开 {panelMeta[nextAction.panel].label}
                    </Button>
                  </div>
                </div>
              </section>

              <section className="lite-panel rounded-[1.8rem] p-5">
                <div className="lite-eyebrow">Readiness</div>
                <h2 className="font-display mt-3 text-2xl font-semibold">执行轨迹</h2>
                <div className="mt-5 space-y-3">
                  {readiness.map((item) => (
                    <div
                      key={item.label}
                      className={cn(
                        'rounded-[1.35rem] border px-4 py-3',
                        item.ready ? 'border-primary/20 bg-primary/8' : 'border-border/80 bg-background/72'
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="font-medium">{item.label}</div>
                        <Badge variant={item.ready ? 'default' : 'outline'}>{item.ready ? '已就绪' : '待完成'}</Badge>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-muted-foreground">{item.detail}</p>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            {review?.summary ? (
              <section className="lite-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="lite-eyebrow">Review Snapshot</div>
                    <h2 className="font-display mt-3 text-2xl font-semibold">当前收口摘要</h2>
                  </div>
                  <Button variant="outline" onClick={() => setActivePanel('review')} className="rounded-full">
                    查看收口
                  </Button>
                </div>
                <pre className="lite-console mt-5 max-h-[18rem] overflow-auto whitespace-pre-wrap">
                  {reviewPreview.text}
                </pre>
              </section>
            ) : null}
          </TabsContent>

          <TabsContent value="sources" className="space-y-4">
            <div className="grid gap-4 2xl:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
              <section className="lite-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-display text-2xl font-semibold">引用封包</h2>
                    <p className="mt-2 text-sm text-muted-foreground">默认只看引用列表，新增时再展开表单。</p>
                  </div>
                  <Button
                    variant={isRefComposerOpen ? 'secondary' : 'outline'}
                    size="sm"
                    onClick={() => setIsRefComposerOpen((prev) => !prev)}
                    className="rounded-full"
                  >
                    <Plus className="h-4 w-4" />
                    添加引用
                  </Button>
                </div>

                {isRefComposerOpen && (
                  <div className="mt-5 rounded-[1.5rem] border border-border/80 bg-background/78 p-4">
                    <div className="grid gap-3">
                      <div className="grid gap-3 sm:grid-cols-[138px_1fr]">
                        <select
                          value={refForm.type}
                          onChange={(e) => setRefForm((prev) => ({ ...prev, type: e.target.value }))}
                          className="h-12 rounded-2xl border border-border/80 bg-background/88 px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <option value="url">URL</option>
                          <option value="repo-path">仓库路径</option>
                          <option value="file">文件路径</option>
                          <option value="work-item">工单</option>
                          <option value="pr">PR</option>
                          <option value="doc">文档</option>
                        </select>
                        <Input
                          className="rounded-2xl border-border/80 bg-background/88"
                          value={refForm.label}
                          onChange={(e) => setRefForm((prev) => ({ ...prev, label: e.target.value }))}
                          placeholder="引用标题"
                        />
                      </div>
                      <Textarea
                        className="min-h-[92px] rounded-[1.35rem] border-border/80 bg-background/88"
                        value={refForm.value}
                        onChange={(e) => setRefForm((prev) => ({ ...prev, value: e.target.value }))}
                        placeholder="URL / 仓库路径 / 文件路径 / 工单 ID"
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button onClick={() => void act(handleAddRef)} className="rounded-full">
                          保存引用
                        </Button>
                        <Button variant="outline" onClick={() => setIsRefComposerOpen(false)} className="rounded-full">
                          收起
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="mt-5 space-y-3">
                  {selectedTask.refs?.map((ref) => (
                    <div key={ref.id} className="rounded-[1.45rem] border border-border/80 bg-background/72 p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline">{ref.type}</Badge>
                            <span className="font-medium">{ref.label}</span>
                          </div>
                          <div className="mt-2 break-all text-sm leading-6 text-muted-foreground">{ref.value}</div>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => void act(() => handleDeleteRef(ref.id))}
                          className="rounded-full text-muted-foreground"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}

                  {!selectedTask.refs?.length && (
                    <div className="rounded-[1.6rem] border border-dashed border-border/80 bg-background/60 p-5 text-sm leading-7 text-muted-foreground">
                      这个任务还没有引用。补上入口后，右侧 Context 才更有价值。
                    </div>
                  )}
                </div>
              </section>

              <section className="lite-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-display text-2xl font-semibold">Context Snapshot</h2>
                    <p className="mt-2 text-sm text-muted-foreground">默认看摘要，长内容按需展开。</p>
                  </div>
                  <Button onClick={() => void act(handleResolveContext)} className="rounded-full">
                    <WandSparkles className="h-4 w-4" />
                    {selectedTask.latestSnapshot ? '重新生成' : '生成 Context'}
                  </Button>
                </div>

                {selectedTask.latestSnapshot ? (
                  <div className="mt-5 rounded-[1.6rem] border border-border/80 bg-background/72 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="text-sm text-muted-foreground">最近生成于 {fmt(selectedTask.latestSnapshot.createdAt)}</div>
                      {snapshotPreview.truncated ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setIsSnapshotExpanded((prev) => !prev)}
                          className="rounded-full"
                        >
                          {isSnapshotExpanded ? (
                            <>
                              收起全文
                              <ChevronUp className="h-4 w-4" />
                            </>
                          ) : (
                            <>
                              展开全文
                              <ChevronDown className="h-4 w-4" />
                            </>
                          )}
                        </Button>
                      ) : null}
                    </div>
                    <pre className="lite-console mt-4 max-h-[34rem] overflow-auto whitespace-pre-wrap">
                      {isSnapshotExpanded ? selectedTask.latestSnapshot.summary : snapshotPreview.text}
                    </pre>
                  </div>
                ) : (
                  <div className="mt-5 rounded-[1.6rem] border border-dashed border-border/80 bg-background/60 p-6 text-sm leading-7 text-muted-foreground">
                    还没有 Context Snapshot。先补引用，再生成上下文。
                  </div>
                )}
              </section>
            </div>
          </TabsContent>

          <TabsContent value="runs" className="space-y-4">
            <div className="grid gap-4 2xl:grid-cols-[360px_minmax(0,1fr)]">
              <section className="lite-panel rounded-[1.8rem] p-5">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-display text-2xl font-semibold">运行队列</h2>
                    <p className="mt-2 text-sm text-muted-foreground">只有进入执行阶段，才展开派发和 run 列表。</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => void act(handleQuickRuns)} className="rounded-full">
                      <Bot className="h-4 w-4" />
                      双 Agent
                    </Button>
                    <Button
                      variant={isRunComposerOpen ? 'secondary' : 'outline'}
                      size="sm"
                      onClick={() => setIsRunComposerOpen((prev) => !prev)}
                      className="rounded-full"
                    >
                      <Plus className="h-4 w-4" />
                      新建 Run
                    </Button>
                  </div>
                </div>

                {isRunComposerOpen && (
                  <div className="mt-5 rounded-[1.5rem] border border-border/80 bg-background/78 p-4">
                    <div className="grid gap-3">
                      <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
                        <Input
                          className="rounded-2xl border-border/80 bg-background/88"
                          value={runForm.name}
                          onChange={(e) => setRunForm((prev) => ({ ...prev, name: e.target.value }))}
                          placeholder="Agent 名称"
                        />
                        <select
                          value={runForm.type}
                          onChange={(e) =>
                            setRunForm((prev) => ({
                              ...prev,
                              type: e.target.value as RunType,
                              name:
                                !prev.name || prev.name === runPresets[prev.type]
                                  ? runPresets[e.target.value as RunType]
                                  : prev.name,
                              command: e.target.value === 'custom' ? prev.command : '',
                            }))
                          }
                          className="h-12 rounded-2xl border border-border/80 bg-background/88 px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          <option value="codex">Codex</option>
                          <option value="claude-code">Claude Code</option>
                          <option value="custom">Custom</option>
                        </select>
                      </div>
                      {runForm.type === 'custom' && (
                        <Textarea
                          className="min-h-[112px] rounded-[1.35rem] border-border/80 bg-background/88"
                          value={runForm.command}
                          onChange={(e) => setRunForm((prev) => ({ ...prev, command: e.target.value }))}
                          placeholder="输入命令。支持 {run_dir}、{execution_cwd}、{prompt_file}、{context_file}。"
                        />
                      )}
                      <div className="flex flex-wrap gap-2">
                        <Button onClick={() => void act(handleCreateRun)} className="rounded-full">
                          创建 Run
                        </Button>
                        <Button variant="outline" onClick={() => setIsRunComposerOpen(false)} className="rounded-full">
                          收起
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                <div className="mt-5 space-y-3">
                  {sortedRuns.map((run) => (
                    <button
                      key={run.id}
                      onClick={() => setSelectedRunId(run.id)}
                      className={cn(
                        'w-full rounded-[1.45rem] border p-4 text-left transition-all',
                        selectedRunId === run.id
                          ? 'border-primary/30 bg-primary/10'
                          : 'border-border/80 bg-background/72 hover:bg-background/88'
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="font-display text-lg font-semibold">{run.agentName}</div>
                          <div className="mt-1 text-sm text-muted-foreground">{run.agentType}</div>
                        </div>
                        <Badge variant={runMeta[run.status][1]}>{runMeta[run.status][0]}</Badge>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        <span>{fmt(run.startedAt || run.createdAt)}</span>
                        {run.errorMessage ? <span>存在错误</span> : null}
                      </div>
                    </button>
                  ))}

                  {!sortedRuns.length && (
                    <div className="rounded-[1.6rem] border border-dashed border-border/80 bg-background/60 p-5 text-sm leading-7 text-muted-foreground">
                      这个任务还没有 Agent run。先派发一条执行线，再查看运行态与产物。
                    </div>
                  )}
                </div>
              </section>

              <section className="lite-panel rounded-[1.8rem] p-5">
                {selectedRun ? (
                  <>
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <div className="lite-eyebrow">Selected Run</div>
                        <h2 className="font-display mt-3 text-2xl font-semibold">{selectedRun.agentName}</h2>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <Badge variant={runMeta[selectedRun.status][1]}>{runMeta[selectedRun.status][0]}</Badge>
                          <Badge variant="outline">{selectedRun.agentType}</Badge>
                          <Badge variant="outline">创建于 {fmt(selectedRun.createdAt)}</Badge>
                        </div>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {selectedRun.status === 'planned' && (
                          <Button variant="outline" size="sm" onClick={() => void act(() => handleStartRun(selectedRun.id))} className="rounded-full">
                            <Play className="h-3.5 w-3.5" />
                            启动
                          </Button>
                        )}
                        {['planned', 'queued', 'running'].includes(selectedRun.status) && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void act(() => handleCancelRun(selectedRun.id))}
                            className="rounded-full"
                          >
                            <Square className="h-3.5 w-3.5" />
                            取消
                          </Button>
                        )}
                        {['failed', 'canceled', 'completed'].includes(selectedRun.status) && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void act(() => handleRetryRun(selectedRun.id))}
                            className="rounded-full"
                          >
                            <RefreshCcw className="h-3.5 w-3.5" />
                            重试
                          </Button>
                        )}
                      </div>
                    </div>

                    {selectedRun.errorMessage && (
                      <div className="mt-5 rounded-[1.35rem] border border-destructive/25 bg-destructive/5 p-4 text-sm text-destructive">
                        {selectedRun.errorMessage}
                      </div>
                    )}

                    <div className="mt-5 rounded-[1.5rem] border border-border/80 bg-background/72 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="text-sm font-medium">Run Artifacts</div>
                          <div className="mt-1 text-sm text-muted-foreground">
                            {['planned', 'queued', 'running'].includes(selectedRun.status)
                              ? '当前 run 正在执行，产物会自动 tail。'
                              : '产物默认折叠，按需展开查看。'}
                          </div>
                        </div>
                        {['planned', 'queued', 'running'].includes(selectedRun.status) ? (
                          <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/78 px-3 py-1.5 text-xs text-muted-foreground">
                            <span className="lite-status-dot" />
                            自动刷新中
                          </div>
                        ) : null}
                      </div>

                      {artifactFilters.length > 1 ? (
                        <div className="mt-4 flex flex-wrap gap-2">
                          {artifactFilters.map((filter) => (
                            <button
                              key={filter}
                              onClick={() => setArtifactFilter(filter)}
                              className={cn(
                                'rounded-full border px-4 py-2 text-sm',
                                artifactFilter === filter
                                  ? 'border-primary/30 bg-primary/10 text-foreground'
                                  : 'border-border/80 bg-background/70 text-muted-foreground'
                              )}
                            >
                              {filter === 'all' ? '全部' : filter}
                            </button>
                          ))}
                        </div>
                      ) : null}

                      {filteredArtifacts.length > 0 ? (
                        <Accordion type="multiple" className="mt-4 rounded-[1.4rem] border border-border/80 bg-background/65 px-4">
                          {filteredArtifacts.map((artifact) => (
                            <AccordionItem key={artifact.id} value={artifact.id} className="border-border/70">
                              <AccordionTrigger className="hover:no-underline">
                                <div className="min-w-0 text-left">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <Badge variant="outline">{artifact.type}</Badge>
                                    <span className="font-medium">{artifact.title}</span>
                                    {liveArtifactTypes.includes(artifact.type as (typeof liveArtifactTypes)[number]) && artifact.truncated ? (
                                      <span className="text-xs text-muted-foreground">tail</span>
                                    ) : null}
                                  </div>
                                  {!!artifact.path && (
                                    <div className="mt-2 truncate text-xs text-muted-foreground">{artifact.path}</div>
                                  )}
                                </div>
                              </AccordionTrigger>
                              <AccordionContent>
                                {typeof artifact.size === 'number' && (
                                  <div className="text-[11px] text-muted-foreground">
                                    {artifact.truncated
                                      ? `显示尾部 20k 字符，源内容约 ${artifact.size} 字符`
                                      : `内容长度 ${artifact.size} 字符`}
                                  </div>
                                )}
                                <pre className="lite-console mt-3 max-h-[30rem] overflow-auto whitespace-pre-wrap">
                                  {artifact.content || '(empty)'}
                                </pre>
                              </AccordionContent>
                            </AccordionItem>
                          ))}
                        </Accordion>
                      ) : (
                        <div className="mt-4 rounded-[1.35rem] border border-dashed border-border/80 bg-background/60 p-5 text-sm leading-7 text-muted-foreground">
                          {['planned', 'queued', 'running'].includes(selectedRun.status)
                            ? 'Run 已启动，等待产物写入。'
                            : '这个 run 还没有产物。'}
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="flex h-full min-h-[24rem] items-center justify-center rounded-[1.6rem] border border-dashed border-border/80 bg-background/60 p-6 text-center text-sm leading-7 text-muted-foreground">
                    从左侧选一个 run，右侧才会展开状态控制和产物细节。
                  </div>
                )}
              </section>
            </div>
          </TabsContent>

          <TabsContent value="review" className="space-y-4">
            <section className="lite-panel rounded-[1.8rem] p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h2 className="font-display text-2xl font-semibold">Review / Compare</h2>
                  <p className="mt-2 text-sm text-muted-foreground">收口阶段只处理结论，不再混入执行期表单和日志。</p>
                </div>
                <Button onClick={() => void act(handleCompare)} className="rounded-full">
                  <GitCompareArrows className="h-4 w-4" />
                  Compare
                </Button>
              </div>

              <div className="mt-5 rounded-[1.5rem] border border-border/80 bg-background/72 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="text-sm font-medium">Review Summary</div>
                  {reviewPreview.truncated ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setIsReviewExpanded((prev) => !prev)}
                      className="rounded-full"
                    >
                      {isReviewExpanded ? (
                        <>
                          收起全文
                          <ChevronUp className="h-4 w-4" />
                        </>
                      ) : (
                        <>
                          展开全文
                          <ChevronDown className="h-4 w-4" />
                        </>
                      )}
                    </Button>
                  ) : null}
                </div>

                {review?.summary ? (
                  <pre className="lite-console mt-4 max-h-[22rem] overflow-auto whitespace-pre-wrap">
                    {isReviewExpanded ? review.summary : reviewPreview.text}
                  </pre>
                ) : (
                  <div className="mt-4 rounded-[1.35rem] border border-dashed border-border/80 bg-background/60 p-5 text-sm leading-7 text-muted-foreground">
                    还没有 review 汇总。等 run 结束后在这里收口。
                  </div>
                )}
              </div>

              <div className="mt-5">
                {comparison.length ? (
                  <div className="grid gap-3 xl:grid-cols-2">
                    {comparison.map((item) => (
                      <div key={item.runId} className="rounded-[1.45rem] border border-border/80 bg-background/72 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div className="font-medium">{item.agentName}</div>
                          <Badge variant={runMeta[item.status as keyof typeof runMeta]?.[1] || 'outline'}>
                            {runMeta[item.status as keyof typeof runMeta]?.[0] || item.status}
                          </Badge>
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                          <span>{item.artifactCount} artifacts</span>
                          <span>{item.changedFiles} files</span>
                          {item.hasPatch ? <span>patch</span> : null}
                          {item.untrackedFiles ? <span>{item.untrackedFiles} untracked</span> : null}
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="rounded-[1.35rem] border border-dashed border-border/80 bg-background/60 p-5 text-sm leading-7 text-muted-foreground">
                    点击 Compare 后，这里才会展示不同 run 的差异摘要。
                  </div>
                )}
              </div>
            </section>
          </TabsContent>
        </Tabs>
      </div>
    );
  }
}
