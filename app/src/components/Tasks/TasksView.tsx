import { useEffect, useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { tasksApi } from '@/lib/api';
import type { AgentRunRecord, WorkspaceTask } from '@/types';

interface ReviewData {
  summary: string;
  runs: AgentRunRecord[];
  artifacts: Array<{ id: string; title: string; type: string }>;
}

interface ComparisonRow {
  runId: string;
  agentName: string;
  status: string;
  artifactCount: number;
  changedFiles: number;
  untrackedFiles: number;
  hasPatch: boolean;
  repoRoot?: string;
}

const liveArtifactTypes = ['stdout', 'stderr', 'summary', 'changes', 'patch'] as const;

const statusTone: Record<string, string> = {
  inbox: 'secondary',
  ready: 'default',
  running: 'default',
  review: 'secondary',
  done: 'outline',
  archived: 'outline',
  planned: 'secondary',
  queued: 'secondary',
  completed: 'outline',
  failed: 'destructive',
  canceled: 'outline',
};

export function TasksView() {
  const [tasks, setTasks] = useState<WorkspaceTask[]>([]);
  const [selectedTask, setSelectedTask] = useState<WorkspaceTask | null>(null);
  const [review, setReview] = useState<ReviewData | null>(null);
  const [comparison, setComparison] = useState<ComparisonRow[]>([]);
  const [selectedRunArtifacts, setSelectedRunArtifacts] = useState<
    Array<{
      id: string;
      title: string;
      type: string;
      content: string;
      path?: string;
      truncated?: boolean;
      size?: number;
    }>
  >([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [taskForm, setTaskForm] = useState({ title: '', description: '' });
  const [refForm, setRefForm] = useState({ type: 'url', label: '', value: '' });
  const [runForm, setRunForm] = useState({ name: 'Codex', type: 'codex', command: '' });

  const loadTasks = async (selectedId?: string) => {
    setIsLoading(true);
    try {
      const response: any = await tasksApi.getAll();
      const nextTasks = response.tasks || [];
      setTasks(nextTasks);

      const nextSelectedId = selectedId || selectedTask?.id || nextTasks[0]?.id;
      if (nextSelectedId) {
        await loadTaskDetail(nextSelectedId);
      } else {
        setSelectedTask(null);
        setReview(null);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const loadTaskDetail = async (taskId: string) => {
    const task: any = await tasksApi.getById(taskId);
    const nextReview: any = await tasksApi.getReview(taskId);
    setSelectedTask(task);
    setReview(nextReview);
  };

  const hasActiveRuns = useMemo(
    () => !!selectedTask?.runs?.some((run) => ['planned', 'queued', 'running'].includes(run.status)),
    [selectedTask]
  );

  const selectedRun = useMemo(
    () => selectedTask?.runs?.find((run) => run.id === selectedRunId) || null,
    [selectedTask, selectedRunId]
  );

  useEffect(() => {
    void loadTasks();
  }, []);

  useEffect(() => {
    if (!selectedTask?.id || !hasActiveRuns) return;

    const timer = window.setInterval(() => {
      void loadTaskDetail(selectedTask.id);
    }, 3000);

    return () => window.clearInterval(timer);
  }, [selectedTask?.id, hasActiveRuns]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRunArtifacts([]);
      return;
    }

    if (!selectedRun) {
      setSelectedRunId(null);
      setSelectedRunArtifacts([]);
    }
  }, [selectedRun, selectedRunId]);

  useEffect(() => {
    if (!selectedRunId || !selectedRun || !['planned', 'queued', 'running'].includes(selectedRun.status)) return;

    const timer = window.setInterval(() => {
      void loadRunArtifacts(selectedRunId, true);
    }, 2000);

    return () => window.clearInterval(timer);
  }, [selectedRun?.status, selectedRunId]);

  const loadRunArtifacts = async (runId: string, tail = false) => {
    const response: any = await tasksApi.getRunArtifacts(runId, tail ? { tail_chars: 20000 } : undefined);
    setSelectedRunArtifacts(response.artifacts || []);
    setSelectedRunId(runId);
  };

  const handleCreateTask = async () => {
    if (!taskForm.title.trim()) return;
    const created: any = await tasksApi.create(taskForm);
    setTaskForm({ title: '', description: '' });
    await loadTasks(created.id);
  };

  const handleAddRef = async () => {
    if (!selectedTask || !refForm.label.trim() || !refForm.value.trim()) return;
    await tasksApi.addRef(selectedTask.id, refForm);
    setRefForm({ type: 'url', label: '', value: '' });
    await loadTaskDetail(selectedTask.id);
  };

  const handleResolveContext = async () => {
    if (!selectedTask) return;
    await tasksApi.resolveContext(selectedTask.id);
    await loadTaskDetail(selectedTask.id);
  };

  const handleCreateRun = async () => {
    if (!selectedTask || !runForm.name.trim()) return;
    await tasksApi.createRuns(selectedTask.id, [runForm]);
    setRunForm({ name: 'Codex', type: 'codex', command: '' });
    await loadTaskDetail(selectedTask.id);
  };

  const handleStartRun = async (runId: string) => {
    await tasksApi.startRun(runId);
    if (selectedTask) await loadTaskDetail(selectedTask.id);
  };

  const handleCancelRun = async (runId: string) => {
    await tasksApi.cancelRun(runId);
    if (selectedTask) await loadTaskDetail(selectedTask.id);
  };

  const handleRetryRun = async (runId: string) => {
    await tasksApi.retryRun(runId);
    if (selectedTask) await loadTaskDetail(selectedTask.id);
  };

  const handleCompare = async () => {
    if (!selectedTask) return;
    const response: any = await tasksApi.compareReview(selectedTask.id);
    setComparison(response.comparison || []);
  };

  const handleViewArtifacts = async (runId: string) => {
    await loadRunArtifacts(runId, false);
  };

  const handleQuickRuns = async () => {
    if (!selectedTask) return;
    await tasksApi.createRuns(selectedTask.id, [
      { name: 'Codex', type: 'codex' },
      { name: 'Claude Code', type: 'claude-code' },
    ]);
    await loadTaskDetail(selectedTask.id);
  };

  return (
    <div className="grid h-full gap-4 p-4 lg:grid-cols-[320px_1fr]">
      <Card className="flex min-h-0 flex-col">
        <CardHeader>
          <CardTitle>任务台</CardTitle>
          <CardDescription>把任务接住，再把多个 Agent 的结果收回来。</CardDescription>
        </CardHeader>
        <CardContent className="flex min-h-0 flex-1 flex-col gap-4">
          <div className="space-y-2">
            <Input
              placeholder="任务标题"
              value={taskForm.title}
              onChange={(e) => setTaskForm((prev) => ({ ...prev, title: e.target.value }))}
            />
            <Textarea
              placeholder="任务描述 / 目标 / 约束"
              value={taskForm.description}
              onChange={(e) => setTaskForm((prev) => ({ ...prev, description: e.target.value }))}
              rows={4}
            />
            <Button onClick={handleCreateTask} className="w-full">
              创建任务
            </Button>
          </div>

          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
            {tasks.map((task) => (
              <button
                key={task.id}
                onClick={() => void loadTaskDetail(task.id)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  selectedTask?.id === task.id ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/60'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-medium">{task.title}</div>
                    <div className="mt-1 text-xs text-muted-foreground line-clamp-2">
                      {task.description || '无描述'}
                    </div>
                  </div>
                  <Badge variant={(statusTone[task.status] as any) || 'secondary'}>{task.status}</Badge>
                </div>
              </button>
            ))}

            {!tasks.length && (
              <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                还没有任务。先创建一个任务卡。
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid min-h-0 gap-4 lg:grid-rows-[auto_auto_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>{selectedTask?.title || '选择一个任务'}</CardTitle>
            <CardDescription>
              {selectedTask ? selectedTask.description || '暂无描述' : '从左侧选择任务查看上下文和运行记录。'}
            </CardDescription>
          </CardHeader>
          {selectedTask && (
            <CardContent className="flex flex-wrap items-center gap-2">
              <Badge variant={(statusTone[selectedTask.status] as any) || 'secondary'}>{selectedTask.status}</Badge>
              <Badge variant="outline">{selectedTask.priority}</Badge>
              <Button variant="outline" size="sm" onClick={handleResolveContext}>
                生成 Context
              </Button>
              <Button variant="outline" size="sm" onClick={handleQuickRuns}>
                快速创建双 Agent Runs
              </Button>
              <Button variant="outline" size="sm" onClick={handleCompare}>
                Compare
              </Button>
              {isLoading && <span className="text-xs text-muted-foreground">加载中...</span>}
              {hasActiveRuns && <span className="text-xs text-muted-foreground">运行中，自动刷新中...</span>}
            </CardContent>
          )}
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>引用</CardTitle>
              <CardDescription>把工作项、链接、文件路径挂到任务上。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-[120px_1fr]">
                <Input
                  value={refForm.type}
                  onChange={(e) => setRefForm((prev) => ({ ...prev, type: e.target.value }))}
                  placeholder="类型"
                />
                <Input
                  value={refForm.label}
                  onChange={(e) => setRefForm((prev) => ({ ...prev, label: e.target.value }))}
                  placeholder="引用标题"
                />
              </div>
              <Input
                value={refForm.value}
                onChange={(e) => setRefForm((prev) => ({ ...prev, value: e.target.value }))}
                placeholder="工作项 ID / URL / 文件路径"
              />
              <Button onClick={handleAddRef} disabled={!selectedTask} className="w-full">
                添加引用
              </Button>

              <div className="space-y-2">
                {selectedTask?.refs?.map((ref) => (
                  <div key={ref.id} className="rounded border p-2 text-sm">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{ref.type}</Badge>
                      <span className="font-medium">{ref.label}</span>
                    </div>
                    <div className="mt-1 break-all text-xs text-muted-foreground">{ref.value}</div>
                  </div>
                ))}
                {!selectedTask?.refs?.length && (
                  <div className="text-sm text-muted-foreground">当前任务还没有引用。</div>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Agent Runs</CardTitle>
              <CardDescription>支持直接拉起 Codex / Claude Code，也支持自定义命令。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  value={runForm.name}
                  onChange={(e) => setRunForm((prev) => ({ ...prev, name: e.target.value }))}
                  placeholder="Agent 名称"
                />
                <Input
                  value={runForm.type}
                  onChange={(e) => setRunForm((prev) => ({ ...prev, type: e.target.value }))}
                  placeholder="Agent 类型"
                />
              </div>
              <Input
                value={runForm.command}
                onChange={(e) => setRunForm((prev) => ({ ...prev, command: e.target.value }))}
                placeholder="可选 command"
              />
              <Button onClick={handleCreateRun} disabled={!selectedTask} className="w-full">
                创建 Run
              </Button>

              <div className="space-y-2">
                {selectedTask?.runs?.map((run) => (
                  <div key={run.id} className="rounded border p-3 text-sm">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="font-medium">{run.agentName}</div>
                        <div className="text-xs text-muted-foreground">{run.agentType}</div>
                      </div>
                      <Badge variant={(statusTone[run.status] as any) || 'secondary'}>{run.status}</Badge>
                    </div>
                    {run.workdir && <div className="mt-2 text-xs text-muted-foreground break-all">{run.workdir}</div>}
                    {run.errorMessage && (
                      <div className="mt-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive">
                        {run.errorMessage}
                      </div>
                    )}
                    <div className="mt-3 flex flex-wrap gap-2">
                      <Button variant="outline" size="sm" onClick={() => handleViewArtifacts(run.id)}>
                        查看产物
                      </Button>
                      {run.status === 'planned' && (
                        <Button variant="outline" size="sm" onClick={() => handleStartRun(run.id)}>
                          启动
                        </Button>
                      )}
                      {['planned', 'queued', 'running'].includes(run.status) && (
                        <Button variant="outline" size="sm" onClick={() => handleCancelRun(run.id)}>
                          取消
                        </Button>
                      )}
                      {['failed', 'canceled', 'completed'].includes(run.status) && (
                        <Button variant="outline" size="sm" onClick={() => handleRetryRun(run.id)}>
                          重试
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
                {!selectedTask?.runs?.length && (
                  <div className="text-sm text-muted-foreground">当前任务还没有 Agent run。</div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        <Card className="min-h-0">
          <CardHeader>
            <CardTitle>Context & Review</CardTitle>
            <CardDescription>查看上下文快照摘要和任务维度的结果收口。</CardDescription>
          </CardHeader>
          <CardContent className="grid min-h-0 gap-4 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-lg border p-3">
              <div className="mb-2 text-sm font-medium">最新 Context</div>
              <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                {selectedTask?.latestSnapshot?.summary || '尚未生成上下文快照。'}
              </pre>
            </div>

            <div className="rounded-lg border p-3">
              <div className="mb-2 text-sm font-medium">Review Summary</div>
              <pre className="max-h-[320px] overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                {review?.summary || '尚无收口结果。'}
              </pre>
              {!!review?.artifacts?.length && (
                <div className="mt-3 space-y-2">
                  {review.artifacts.slice(0, 6).map((artifact) => (
                    <div key={artifact.id} className="rounded border border-dashed p-2 text-xs">
                      <span className="font-medium">{artifact.title}</span>
                      <span className="ml-2 text-muted-foreground">{artifact.type}</span>
                    </div>
                  ))}
                </div>
              )}
              {!!comparison.length && (
                <div className="mt-4 space-y-2 border-t pt-3">
                  <div className="text-sm font-medium">Compare Result</div>
                  {comparison.map((item) => (
                    <div key={item.runId} className="rounded border border-dashed p-2 text-xs">
                      <span className="font-medium">{item.agentName}</span>
                      <span className="ml-2 text-muted-foreground">{item.status}</span>
                      <span className="ml-2 text-muted-foreground">artifacts: {item.artifactCount}</span>
                      <span className="ml-2 text-muted-foreground">files: {item.changedFiles}</span>
                      {item.hasPatch && <span className="ml-2 text-muted-foreground">patch</span>}
                      {!!item.untrackedFiles && (
                        <span className="ml-2 text-muted-foreground">untracked: {item.untrackedFiles}</span>
                      )}
                      {!!item.repoRoot && (
                        <div className="mt-1 break-all text-[11px] text-muted-foreground">{item.repoRoot}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {!!selectedRunArtifacts.length && (
          <Card className="min-h-0">
            <CardHeader>
              <CardTitle>Run Artifacts</CardTitle>
              <CardDescription>
                Run: {selectedRunId}
                {selectedRun && ` · ${selectedRun.status}`}
                {selectedRun && ['planned', 'queued', 'running'].includes(selectedRun.status) && ' · 实时 tail 中'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {selectedRunArtifacts.map((artifact) => (
                <div key={artifact.id} className="rounded-lg border p-3">
                  <div className="mb-2 flex items-center gap-2 text-sm">
                    <Badge variant="outline">{artifact.type}</Badge>
                    <span className="font-medium">{artifact.title}</span>
                    {liveArtifactTypes.includes(artifact.type as (typeof liveArtifactTypes)[number]) && artifact.truncated && (
                      <span className="text-xs text-muted-foreground">tail</span>
                    )}
                  </div>
                  {!!artifact.path && (
                    <div className="mb-2 break-all text-xs text-muted-foreground">{artifact.path}</div>
                  )}
                  {typeof artifact.size === 'number' && (
                    <div className="mb-2 text-[11px] text-muted-foreground">
                      {artifact.truncated ? `显示尾部 20k 字符，源内容约 ${artifact.size} 字符` : `内容长度 ${artifact.size} 字符`}
                    </div>
                  )}
                  <pre className="max-h-[240px] overflow-auto whitespace-pre-wrap text-xs text-muted-foreground">
                    {artifact.content || '(empty)'}
                  </pre>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
