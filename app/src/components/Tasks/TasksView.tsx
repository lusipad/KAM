import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  Bot,
  FileSearch,
  FolderInput,
  GitCompareArrows,
  LoaderCircle,
  Play,
  RefreshCcw,
  Sparkles,
  Square,
  Trash2,
  WandSparkles,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { tasksApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { AgentRunRecord, ComparisonRow, ReviewData, RunArtifactView, WorkspaceTask } from '@/types';

type RunType = 'codex' | 'claude-code' | 'custom';
type BadgeVariant = 'default' | 'secondary' | 'outline' | 'destructive';

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

const runPresets: Record<RunType, string> = {
  codex: 'Codex',
  'claude-code': 'Claude Code',
  custom: 'Custom Command',
};

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

const liveArtifactTypes = ['stdout', 'stderr', 'summary', 'changes', 'patch'] as const;

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

export function TasksView() {
  const initialLoadRef = useRef(false);
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [selectedTask, setSelectedTask] = useState<WorkspaceTask | null>(null);
  const [review, setReview] = useState<ReviewData | null>(null);
  const [comparison, setComparison] = useState<ComparisonRow[]>([]);
  const [selectedRunArtifacts, setSelectedRunArtifacts] = useState<RunArtifactView[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [artifactFilter, setArtifactFilter] = useState('all');
  const [isLoading, setIsLoading] = useState(false);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [taskForm, setTaskForm] = useState<{
    title: string;
    description: string;
    priority: WorkspaceTask['priority'];
  }>({ title: '', description: '', priority: 'medium' });
  const [refForm, setRefForm] = useState({ type: 'url', label: '', value: '' });
  const [runForm, setRunForm] = useState<{ name: string; type: RunType; command: string }>({
    name: 'Codex',
    type: 'codex',
    command: '',
  });

  useEffect(() => {
    if (initialLoadRef.current) return;
    initialLoadRef.current = true;
    void loadTasks();
  }, [loadTasks]);

  const selectedRun = useMemo(
    () => selectedTask?.runs?.find((run) => run.id === selectedRunId) || null,
    [selectedTask, selectedRunId]
  );

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

  useEffect(() => {
    if (!selectedTask?.id || !hasActiveRuns) return;
    const timer = window.setInterval(() => void loadTaskDetail(selectedTask.id), 3000);
    return () => window.clearInterval(timer);
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
  }, [selectedRunId, selectedRunStatus]);

  useEffect(() => {
    if (selectedRunId && !selectedRun) {
      setSelectedRunId(null);
      setSelectedRunArtifacts([]);
      setArtifactFilter('all');
    }
  }, [selectedRun, selectedRunId]);

  const flow = [
    !!selectedTask,
    !!selectedTask?.refs?.length,
    !!selectedTask?.latestSnapshot,
    !!selectedTask?.runs?.length,
    !!comparison.length || !!review?.summary,
  ];

  return (
    <div className="space-y-5">
      <section className="lite-panel rounded-[2rem] p-6 lg:p-8">
        <div className="grid gap-8 xl:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="lite-eyebrow">Task to Result</div>
            <h1 className="font-display mt-4 text-4xl font-semibold leading-tight md:text-5xl">
              {selectedTask ? selectedTask.title : '把任务放回一条清晰的执行线。'}
            </h1>
            <p className="mt-4 max-w-[60ch] text-sm leading-7 text-muted-foreground md:text-base">
              {selectedTask
                ? selectedTask.description || '当前任务还没有补充描述。'
                : '左侧负责任务池，中间锁定当前任务，右侧专门处理 Agent Runs 和结果收口。'}
            </p>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button onClick={() => void act(handleResolveContext)} disabled={!selectedTask} className="rounded-full px-5">
                <WandSparkles className="h-4 w-4" />
                生成 Context
              </Button>
              <Button variant="outline" onClick={() => void act(handleQuickRuns)} disabled={!selectedTask} className="rounded-full px-5">
                <Bot className="h-4 w-4" />
                双 Agent
              </Button>
              <Button variant="outline" onClick={() => void act(handleCompare)} disabled={!selectedTask} className="rounded-full px-5">
                <GitCompareArrows className="h-4 w-4" />
                Compare
              </Button>
              {hasActiveRuns && (
                <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/70 px-4 py-2 text-sm text-muted-foreground">
                  <span className="lite-status-dot" />
                  自动刷新中
                </div>
              )}
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              {['任务卡', '引用', 'Snapshot', 'Runs', 'Compare'].map((label, index) => (
                <div key={label} className="flex items-center gap-3">
                  <div
                    className={cn(
                      'rounded-full border px-4 py-2 text-sm',
                      flow[index] ? 'border-primary/25 bg-primary/10 text-foreground' : 'border-border/80 bg-background/65 text-muted-foreground'
                    )}
                  >
                    {label}
                  </div>
                  {index < 4 && <ArrowRight className="h-4 w-4 text-muted-foreground" />}
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-[1.6rem] border border-border/70 bg-background/72 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Tasks</div>
              <div className="font-display mt-3 text-3xl font-semibold">{tasks.length}</div>
            </div>
            <div className="rounded-[1.6rem] border border-border/70 bg-background/72 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Refs</div>
              <div className="font-display mt-3 text-3xl font-semibold">{selectedTask?.refs?.length || 0}</div>
            </div>
            <div className="rounded-[1.6rem] border border-border/70 bg-background/72 p-4">
              <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">Runs</div>
              <div className="font-display mt-3 text-3xl font-semibold">{selectedTask?.runs?.length || 0}</div>
            </div>
            <div className="rounded-[1.6rem] border border-border/70 bg-foreground p-4 text-background">
              <div className="text-xs uppercase tracking-[0.18em] text-background/60">Review</div>
              <div className="font-display mt-3 text-xl font-semibold">
                {selectedTask ? taskMeta[selectedTask.status][0] : '等待选中'}
              </div>
            </div>
          </div>
        </div>
      </section>

      {errorMessage && (
        <div className="lite-panel rounded-[1.6rem] border-destructive/20 bg-destructive/5 px-5 py-4 text-sm text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)_390px]">
        {renderTaskPool()}
        {renderFocusLane()}
        {renderRunLane()}
      </div>

      {(selectedRunId || !!selectedRunArtifacts.length) && renderArtifacts()}
    </div>
  );

  // Initial bootstrap intentionally calls this local helper once from the mount effect.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  async function loadTasks(selectedId?: string) {
    setIsLoading(true);
    try {
      setErrorMessage(null);
      const response = await tasksApi.getAll();
      const nextTasks = response.tasks || [];
      setTasks(nextTasks);
      const nextSelectedId = selectedId || selectedTask?.id || nextTasks[0]?.id;
      if (nextSelectedId) await loadTaskDetail(nextSelectedId);
      else {
        setSelectedTask(null);
        setReview(null);
        setSelectedRunId(null);
        setSelectedRunArtifacts([]);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsLoading(false);
      setIsBootstrapping(false);
    }
  }

  async function loadTaskDetail(taskId: string) {
    try {
      setErrorMessage(null);
      const task = await tasksApi.getById(taskId);
      const nextReview = await tasksApi.getReview(taskId);
      setSelectedTask(task);
      setReview(nextReview);
      setComparison([]);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function loadRunArtifacts(runId: string, tail = false) {
    try {
      setErrorMessage(null);
      const response = await tasksApi.getRunArtifacts(runId, tail ? { tail_chars: 20000 } : undefined);
      setSelectedRunArtifacts(response.artifacts || []);
      setSelectedRunId(runId);
      setArtifactFilter('all');
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
    await loadTaskDetail(taskId);
  }

  async function handleResolveContext() {
    if (!selectedTask) return;
    await tasksApi.resolveContext(selectedTask.id);
    await loadTaskDetail(selectedTask.id);
  }

  async function handleQuickRuns() {
    if (!selectedTask) return;
    await tasksApi.createRuns(selectedTask.id, [
      { name: 'Codex', type: 'codex' },
      { name: 'Claude Code', type: 'claude-code' },
    ]);
    await loadTaskDetail(selectedTask.id);
  }

  async function handleCreateRun() {
    if (!selectedTask || !runForm.name.trim()) return;
    if (runForm.type === 'custom' && !runForm.command.trim()) return;
    await tasksApi.createRuns(selectedTask.id, [runForm]);
    setRunForm({ name: 'Codex', type: 'codex', command: '' });
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
    const response = await tasksApi.compareReview(selectedTask.id);
    setComparison(response.comparison || []);
  }

  async function handleAddRef() {
    if (!selectedTask || !refForm.label.trim() || !refForm.value.trim()) return;
    await tasksApi.addRef(selectedTask.id, refForm);
    setRefForm({ type: 'url', label: '', value: '' });
    await loadTaskDetail(selectedTask.id);
  }

  function renderTaskPool() {
    return (
      <section className="lite-panel flex min-h-[32rem] flex-col rounded-[2rem] p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-display text-2xl font-semibold">任务池</h2>
            <p className="mt-2 text-sm text-muted-foreground">先定焦，再进入执行。</p>
          </div>
          {isLoading && <LoaderCircle className="h-5 w-5 animate-spin text-muted-foreground" />}
        </div>
        <div className="mt-5 grid gap-3">
          <Input
            className="rounded-2xl border-border/80 bg-background/80"
            placeholder="任务标题"
            value={taskForm.title}
            onChange={(e) => setTaskForm((prev) => ({ ...prev, title: e.target.value }))}
          />
          <div className="grid gap-3 sm:grid-cols-[1fr_124px]">
            <Textarea
              className="min-h-[104px] rounded-[1.4rem] border-border/80 bg-background/80"
              placeholder="任务描述 / 目标 / 约束"
              value={taskForm.description}
              onChange={(e) => setTaskForm((prev) => ({ ...prev, description: e.target.value }))}
            />
            <select
              value={taskForm.priority}
              onChange={(e) =>
                setTaskForm((prev) => ({ ...prev, priority: e.target.value as WorkspaceTask['priority'] }))
              }
              className="h-12 rounded-2xl border border-border/80 bg-background/80 px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="low">低优先级</option>
              <option value="medium">中优先级</option>
              <option value="high">高优先级</option>
            </select>
          </div>
          <Button onClick={() => void act(handleCreateTask)} className="rounded-full">
            创建任务
          </Button>
        </div>
        <div className="my-5 lite-soft-divider" />
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
          {isBootstrapping &&
            Array.from({ length: 4 }).map((_, index) => (
              <div
                key={index}
                className="h-28 animate-pulse rounded-[1.6rem] border border-border/70 bg-background/60"
              />
            ))}
          {!isBootstrapping &&
            tasks.map((task) => (
              <button
                key={task.id}
                onClick={() => void handleSelectTask(task.id)}
                className={cn(
                  'w-full rounded-[1.7rem] border p-4 text-left transition-all',
                  selectedTask?.id === task.id
                    ? 'border-primary/30 bg-primary/10'
                    : 'border-border/80 bg-background/70 hover:bg-background/90'
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-display line-clamp-2 text-lg font-semibold">{task.title}</div>
                    <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">
                      {task.description || '还没有补充描述。'}
                    </p>
                  </div>
                  <Badge variant={taskMeta[task.status][1]}>{taskMeta[task.status][0]}</Badge>
                </div>
                <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span>{task.refs?.length || 0} refs</span>
                  <span>{task.runs?.length || 0} runs</span>
                  <span>{fmt(task.updatedAt)}</span>
                </div>
              </button>
            ))}
          {!isBootstrapping && !tasks.length && (
            <div className="rounded-[1.8rem] border border-dashed border-border/80 bg-background/55 p-6 text-sm leading-7 text-muted-foreground">
              这里还没有任务。先把当前最重要的一件事接进来。
            </div>
          )}
        </div>
      </section>
    );
  }

  function renderFocusLane() {
    return (
      <div className="space-y-5">
        <section className="lite-panel rounded-[2rem] p-6">
          {selectedTask ? (
            <>
              <div className="lite-eyebrow">Task Focus</div>
              <h2 className="font-display mt-3 text-3xl font-semibold">{selectedTask.title}</h2>
              <p className="mt-3 text-sm leading-7 text-muted-foreground">
                {selectedTask.description || '当前任务还没有补充描述。'}
              </p>
              <div className="mt-5 flex flex-wrap gap-2">
                <Badge variant={taskMeta[selectedTask.status][1]}>{taskMeta[selectedTask.status][0]}</Badge>
                <Badge variant="outline">{selectedTask.priority}</Badge>
                <Badge variant="outline">{selectedTask.refs?.length || 0} refs</Badge>
                <Badge variant="outline">{selectedTask.runs?.length || 0} runs</Badge>
              </div>
            </>
          ) : (
            <div className="rounded-[1.8rem] border border-dashed border-border/80 bg-background/55 p-8 text-sm leading-7 text-muted-foreground">
              先从左侧选择一个任务，中间区域只围绕这个任务展开。
            </div>
          )}
        </section>

        <div className="grid gap-5 2xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <section className="lite-panel rounded-[2rem] p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-display text-2xl font-semibold">引用封包</h3>
                <p className="mt-2 text-sm text-muted-foreground">只保留当前任务真正需要的入口。</p>
              </div>
              <FolderInput className="h-5 w-5 text-muted-foreground" />
            </div>
            <div className="mt-5 grid gap-3">
              <div className="grid gap-3 sm:grid-cols-[138px_1fr]">
                <select
                  value={refForm.type}
                  onChange={(e) => setRefForm((prev) => ({ ...prev, type: e.target.value }))}
                  className="h-12 rounded-2xl border border-border/80 bg-background/80 px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="url">URL</option>
                  <option value="repo-path">仓库路径</option>
                  <option value="file">文件路径</option>
                  <option value="work-item">工单</option>
                  <option value="pr">PR</option>
                  <option value="doc">文档</option>
                </select>
                <Input
                  className="rounded-2xl border-border/80 bg-background/80"
                  value={refForm.label}
                  onChange={(e) => setRefForm((prev) => ({ ...prev, label: e.target.value }))}
                  placeholder="引用标题"
                />
              </div>
              <Textarea
                className="min-h-[88px] rounded-[1.4rem] border-border/80 bg-background/80"
                value={refForm.value}
                onChange={(e) => setRefForm((prev) => ({ ...prev, value: e.target.value }))}
                placeholder="URL / 仓库路径 / 文件路径 / 工单 ID"
              />
              <Button onClick={() => void act(handleAddRef)} disabled={!selectedTask} className="rounded-full">
                添加引用
              </Button>
            </div>
            <div className="my-5 lite-soft-divider" />
            <div className="space-y-3">
              {selectedTask?.refs?.map((ref) => (
                <div key={ref.id} className="rounded-[1.5rem] border border-border/80 bg-background/72 p-4">
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
              {!selectedTask?.refs?.length && (
                <div className="rounded-[1.6rem] border border-dashed border-border/80 bg-background/55 p-5 text-sm text-muted-foreground">
                  这个任务还没有引用。
                </div>
              )}
            </div>
          </section>
          <section className="lite-panel rounded-[2rem] p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-display text-2xl font-semibold">Context Snapshot</h3>
                <p className="mt-2 text-sm text-muted-foreground">任务、引用、最近运行，三类信息收敛到一起。</p>
              </div>
              <FileSearch className="h-5 w-5 text-muted-foreground" />
            </div>
            {selectedTask?.latestSnapshot ? (
              <div className="mt-5 space-y-4">
                <div className="rounded-[1.5rem] border border-border/80 bg-background/72 p-4 text-sm text-muted-foreground">
                  最近生成于 {fmt(selectedTask.latestSnapshot.createdAt)}
                </div>
                <pre className="lite-console max-h-[32rem] overflow-auto whitespace-pre-wrap">
                  {selectedTask.latestSnapshot.summary}
                </pre>
              </div>
            ) : (
              <div className="mt-5 rounded-[1.6rem] border border-dashed border-border/80 bg-background/55 p-6 text-sm leading-7 text-muted-foreground">
                还没有 Context Snapshot。先补引用，再生成上下文。
              </div>
            )}
          </section>
        </div>
      </div>
    );
  }

  function renderRunLane() {
    return (
      <div className="space-y-5">
        <section className="lite-panel rounded-[2rem] p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-display text-2xl font-semibold">Dispatch</h3>
              <p className="mt-2 text-sm text-muted-foreground">从这里派发不同 Agent。</p>
            </div>
            <Sparkles className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="mt-5 grid gap-3">
            <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
              <Input
                className="rounded-2xl border-border/80 bg-background/80"
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
                    name: !prev.name || prev.name === runPresets[prev.type] ? runPresets[e.target.value as RunType] : prev.name,
                    command: e.target.value === 'custom' ? prev.command : '',
                  }))
                }
                className="h-12 rounded-2xl border border-border/80 bg-background/80 px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="codex">Codex</option>
                <option value="claude-code">Claude Code</option>
                <option value="custom">Custom</option>
              </select>
            </div>
            {runForm.type === 'custom' && (
              <Textarea
                className="min-h-[112px] rounded-[1.4rem] border-border/80 bg-background/80"
                value={runForm.command}
                onChange={(e) => setRunForm((prev) => ({ ...prev, command: e.target.value }))}
                placeholder="输入命令。支持 {run_dir}、{execution_cwd}、{prompt_file}、{context_file}。"
              />
            )}
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => void act(handleCreateRun)} disabled={!selectedTask} className="rounded-full px-5">
                创建 Run
              </Button>
              <Button variant="outline" onClick={() => void act(handleQuickRuns)} disabled={!selectedTask} className="rounded-full px-5">
                Codex + Claude
              </Button>
            </div>
          </div>
        </section>

        <section className="lite-panel rounded-[2rem] p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-display text-2xl font-semibold">Agent Runs</h3>
              <p className="mt-2 text-sm text-muted-foreground">右侧只看运行状态和控制动作。</p>
            </div>
            <Bot className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="mt-5 space-y-3">
            {selectedTask?.runs?.map((run) => (
              <div
                key={run.id}
                className={cn(
                  'rounded-[1.6rem] border p-4',
                  selectedRunId === run.id ? 'border-primary/30 bg-primary/10' : 'border-border/80 bg-background/70'
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-display text-lg font-semibold">{run.agentName}</div>
                    <div className="mt-1 text-sm text-muted-foreground">{run.agentType}</div>
                  </div>
                  <Badge variant={runMeta[run.status][1]}>{runMeta[run.status][0]}</Badge>
                </div>
                {run.errorMessage && (
                  <div className="mt-3 rounded-[1rem] border border-destructive/25 bg-destructive/5 p-3 text-xs text-destructive">
                    {run.errorMessage}
                  </div>
                )}
                <div className="mt-4 flex flex-wrap gap-2">
                  <Button variant="outline" size="sm" onClick={() => void loadRunArtifacts(run.id)} className="rounded-full">
                    查看产物
                  </Button>
                  {run.status === 'planned' && (
                    <Button variant="outline" size="sm" onClick={() => void act(() => handleStartRun(run.id))} className="rounded-full">
                      <Play className="h-3.5 w-3.5" />
                      启动
                    </Button>
                  )}
                  {['planned', 'queued', 'running'].includes(run.status) && (
                    <Button variant="outline" size="sm" onClick={() => void act(() => handleCancelRun(run.id))} className="rounded-full">
                      <Square className="h-3.5 w-3.5" />
                      取消
                    </Button>
                  )}
                  {['failed', 'canceled', 'completed'].includes(run.status) && (
                    <Button variant="outline" size="sm" onClick={() => void act(() => handleRetryRun(run.id))} className="rounded-full">
                      <RefreshCcw className="h-3.5 w-3.5" />
                      重试
                    </Button>
                  )}
                </div>
              </div>
            ))}
            {!selectedTask?.runs?.length && (
              <div className="rounded-[1.6rem] border border-dashed border-border/80 bg-background/55 p-5 text-sm text-muted-foreground">
                这个任务还没有 Agent run。
              </div>
            )}
          </div>
        </section>

        <section className="lite-panel rounded-[2rem] p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h3 className="font-display text-2xl font-semibold">Review / Compare</h3>
              <p className="mt-2 text-sm text-muted-foreground">把各条执行线收回到任务维度。</p>
            </div>
            <Button variant="outline" onClick={() => void act(handleCompare)} disabled={!selectedTask} className="rounded-full">
              <GitCompareArrows className="h-4 w-4" />
              Compare
            </Button>
          </div>
          <div className="mt-5 space-y-4">
            <pre className="lite-console max-h-[16rem] overflow-auto whitespace-pre-wrap">
              {review?.summary || '还没有 review 汇总。'}
            </pre>
            {!!comparison.length &&
              comparison.map((item) => (
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
                    {item.hasPatch && <span>patch</span>}
                    {!!item.untrackedFiles && <span>{item.untrackedFiles} untracked</span>}
                  </div>
                </div>
              ))}
          </div>
        </section>
      </div>
    );
  }

  function renderArtifacts() {
    return (
      <section className="lite-panel rounded-[2rem] p-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <div className="lite-eyebrow">Run Artifacts</div>
            <h2 className="font-display mt-3 text-3xl font-semibold">{selectedRun?.agentName || '已选择 Run'}</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {selectedRun && ['planned', 'queued', 'running'].includes(selectedRun.status)
                ? '当前 run 正在执行，产物会自动 tail。'
                : '这里展示当前 run 的关键输出。'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {artifactFilters.map((filter) => (
              <button
                key={filter}
                onClick={() => setArtifactFilter(filter)}
                className={cn(
                  'rounded-full border px-4 py-2 text-sm',
                  artifactFilter === filter
                    ? 'border-primary/30 bg-primary/10 text-foreground'
                    : 'border-border/80 bg-background/65 text-muted-foreground'
                )}
              >
                {filter === 'all' ? '全部' : filter}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-6 grid gap-4 xl:grid-cols-2">
          {filteredArtifacts.map((artifact) => (
            <div
              key={artifact.id}
              className={cn(
                'rounded-[1.7rem] border border-border/80 bg-background/72 p-4',
                ['summary', 'patch', 'changes'].includes(artifact.type) && 'xl:col-span-2'
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">{artifact.type}</Badge>
                <span className="font-medium">{artifact.title}</span>
                {liveArtifactTypes.includes(artifact.type as (typeof liveArtifactTypes)[number]) && artifact.truncated && (
                  <span className="text-xs text-muted-foreground">tail</span>
                )}
              </div>
              {!!artifact.path && <div className="mt-2 break-all text-xs text-muted-foreground">{artifact.path}</div>}
              {typeof artifact.size === 'number' && (
                <div className="mt-2 text-[11px] text-muted-foreground">
                  {artifact.truncated ? `显示尾部 20k 字符，源内容约 ${artifact.size} 字符` : `内容长度 ${artifact.size} 字符`}
                </div>
              )}
              <pre className="lite-console mt-4 max-h-[28rem] overflow-auto whitespace-pre-wrap">
                {artifact.content || '(empty)'}
              </pre>
            </div>
          ))}
        </div>
      </section>
    );
  }
}
