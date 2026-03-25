import { useEffect, useMemo, useState } from 'react';
import {
  BadgeCheck,
  Bot,
  CircleOff,
  Gauge,
  LoaderCircle,
  PauseCircle,
  Play,
  Plus,
  RefreshCcw,
  Rocket,
  TriangleAlert,
} from 'lucide-react';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { autonomyApi } from '@/lib/api';
import { cn } from '@/lib/utils';
import type {
  AutonomyCheckCommand,
  AutonomyMetrics,
  AutonomySession,
  AutonomySessionCreateInput,
  WorkspaceTask,
} from '@/types';

interface AutonomyPanelProps {
  task: WorkspaceTask;
  onTaskRefresh?: () => void;
}

const sessionMeta = {
  draft: ['草稿', 'secondary'],
  running: ['执行中', 'default'],
  completed: ['已完成', 'outline'],
  failed: ['失败', 'destructive'],
  interrupted: ['已打断', 'secondary'],
} as const;

function pct(value: number) {
  return `${Math.round(value * 100)}%`;
}

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

function defaultCheck(): AutonomyCheckCommand {
  return { label: '', command: '' };
}

function getErrorMessage(error: unknown) {
  return error instanceof Error && error.message ? error.message : '自治会话请求失败，请稍后重试。';
}

export function AutonomyPanel({ task, onTaskRefresh }: AutonomyPanelProps) {
  const [sessions, setSessions] = useState<AutonomySession[]>([]);
  const [globalMetrics, setGlobalMetrics] = useState<AutonomyMetrics | null>(null);
  const [taskMetrics, setTaskMetrics] = useState<AutonomyMetrics | null>(null);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [isDogfooding, setIsDogfooding] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isComposerOpen, setIsComposerOpen] = useState(false);
  const [form, setForm] = useState<AutonomySessionCreateInput>({
    title: `${task.title} / 自治会话`,
    objective: task.description || '',
    primaryAgentName: 'Codex',
    primaryAgentType: 'codex',
    maxIterations: 3,
    successCriteria: '完成任务并通过所有检查。',
    checkCommands: [defaultCheck()],
  });

  const selectedSession = useMemo(
    () => sessions.find((session) => session.id === selectedSessionId) || sessions[0] || null,
    [sessions, selectedSessionId]
  );

  const hasRunningSession = useMemo(() => sessions.some((session) => session.status === 'running'), [sessions]);

  useEffect(() => {
    setForm({
      title: `${task.title} / 自治会话`,
      objective: task.description || '',
      primaryAgentName: 'Codex',
      primaryAgentType: 'codex',
      maxIterations: 3,
      successCriteria: '完成任务并通过所有检查。',
      checkCommands: [defaultCheck()],
    });
    setSelectedSessionId(null);
    setIsComposerOpen(false);
    void loadAutonomy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task.id]);

  useEffect(() => {
    if (!hasRunningSession) return;
    const timer = window.setInterval(() => void loadAutonomy({ silent: true }), 3000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasRunningSession, task.id]);

  async function loadAutonomy(options?: { silent?: boolean }) {
    if (!options?.silent) setIsLoading(true);
    try {
      setErrorMessage(null);
      const [taskSessionResponse, nextGlobalMetrics, nextTaskMetrics] = await Promise.all([
        autonomyApi.listTaskSessions(task.id),
        autonomyApi.getMetrics(),
        autonomyApi.getTaskMetrics(task.id),
      ]);

      const nextSessions = taskSessionResponse.sessions || [];
      setSessions(nextSessions);
      setGlobalMetrics(nextGlobalMetrics);
      setTaskMetrics(nextTaskMetrics);
      setSelectedSessionId((prev) => (prev && nextSessions.some((item) => item.id === prev) ? prev : nextSessions[0]?.id || null));

      if (nextSessions.some((session) => session.status === 'running')) onTaskRefresh?.();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      if (!options?.silent) setIsLoading(false);
    }
  }

  async function handleCreateSession() {
    setIsCreating(true);
    try {
      setErrorMessage(null);
      const payload: AutonomySessionCreateInput = {
        ...form,
        checkCommands: (form.checkCommands || []).filter((item) => item.label.trim() && item.command.trim()),
      };
      const created = await autonomyApi.createTaskSession(task.id, payload);
      setSelectedSessionId(created.id);
      setIsComposerOpen(false);
      await loadAutonomy();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsCreating(false);
    }
  }

  async function handleCreateAndStartDogfood() {
    setIsDogfooding(true);
    try {
      setErrorMessage(null);
      const created = await autonomyApi.createDogfoodSession(task.id);
      await autonomyApi.startSession(created.id);
      setSelectedSessionId(created.id);
      await loadAutonomy();
      onTaskRefresh?.();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsDogfooding(false);
    }
  }

  async function handleStartSession(sessionId: string) {
    try {
      setErrorMessage(null);
      await autonomyApi.startSession(sessionId);
      await loadAutonomy();
      onTaskRefresh?.();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  async function handleInterruptSession(sessionId: string) {
    try {
      setErrorMessage(null);
      await autonomyApi.interruptSession(sessionId);
      await loadAutonomy();
      onTaskRefresh?.();
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    }
  }

  function updateCheck(index: number, field: keyof AutonomyCheckCommand, value: string) {
    setForm((prev) => ({
      ...prev,
      checkCommands: (prev.checkCommands || []).map((item, currentIndex) =>
        currentIndex === index ? { ...item, [field]: value } : item
      ),
    }));
  }

  function addCheckRow() {
    setForm((prev) => ({
      ...prev,
      checkCommands: [...(prev.checkCommands || []), defaultCheck()],
    }));
  }

  function removeCheckRow(index: number) {
    setForm((prev) => ({
      ...prev,
      checkCommands: (prev.checkCommands || []).filter((_, currentIndex) => currentIndex !== index),
    }));
  }

  const metricCards = [
    {
      label: '自主完成率',
      value: pct(globalMetrics?.autonomyCompletionRate || 0),
      helper: `当前任务 ${pct(taskMetrics?.autonomyCompletionRate || 0)}`,
      icon: Gauge,
    },
    {
      label: '打断率',
      value: pct(globalMetrics?.interruptionRate || 0),
      helper: `当前任务 ${pct(taskMetrics?.interruptionRate || 0)}`,
      icon: PauseCircle,
    },
    {
      label: '完成成功率',
      value: pct(globalMetrics?.successRate || 0),
      helper: `当前任务 ${pct(taskMetrics?.successRate || 0)}`,
      icon: BadgeCheck,
    },
    {
      label: '完成平均轮次',
      value: `${(globalMetrics?.averageCompletedIterations || 0).toFixed(1)} 轮`,
      helper: `当前任务 ${(taskMetrics?.averageCompletedIterations || 0).toFixed(1)} 轮`,
      icon: RefreshCcw,
    },
  ];

  return (
    <div className="space-y-4">
      {errorMessage && (
        <div className="rounded-[1.5rem] border border-destructive/20 bg-destructive/5 px-5 py-4 text-sm text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-4">
        {metricCards.map((item) => {
          const Icon = item.icon;
          return (
            <section key={item.label} className="lite-panel rounded-[1.5rem] p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="text-sm text-muted-foreground">{item.label}</div>
                <Icon className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="font-display mt-3 text-3xl font-semibold">{item.value}</div>
              <div className="mt-2 text-sm text-muted-foreground">{item.helper}</div>
            </section>
          );
        })}
      </div>

      <section className="lite-panel rounded-[1.8rem] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="lite-eyebrow">Autonomy Loop</div>
            <h2 className="font-display mt-3 text-2xl font-semibold">让 AI 持续做事，再用检查系统自己验收。</h2>
            <p className="mt-2 max-w-[72ch] text-sm leading-7 text-muted-foreground">
              这里不只是“拉起一次 run”，而是让同一个任务自动迭代，直到通过检查、被打断，或达到上限。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => void handleCreateAndStartDogfood()} disabled={isDogfooding} className="rounded-full">
              {isDogfooding ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Rocket className="h-4 w-4" />}
              启动 KAM Dogfood
            </Button>
            <Button
              variant={isComposerOpen ? 'secondary' : 'outline'}
              onClick={() => setIsComposerOpen((prev) => !prev)}
              className="rounded-full"
            >
              <Plus className="h-4 w-4" />
              新建自治会话
            </Button>
          </div>
        </div>

        {isComposerOpen && (
          <div className="mt-5 rounded-[1.6rem] border border-border/80 bg-background/72 p-4">
            <div className="grid gap-3">
              <Input
                value={form.title || ''}
                onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))}
                placeholder="会话标题"
                className="rounded-2xl border-border/80 bg-background/88"
              />
              <Textarea
                value={form.objective || ''}
                onChange={(event) => setForm((prev) => ({ ...prev, objective: event.target.value }))}
                placeholder="希望 AI 自主完成什么"
                className="min-h-[96px] rounded-[1.35rem] border-border/80 bg-background/88"
              />
              <div className="grid gap-3 lg:grid-cols-[1fr_180px_180px]">
                <Input
                  value={form.primaryAgentName || ''}
                  onChange={(event) => setForm((prev) => ({ ...prev, primaryAgentName: event.target.value }))}
                  placeholder="主 Agent 名称"
                  className="rounded-2xl border-border/80 bg-background/88"
                />
                <select
                  value={form.primaryAgentType || 'codex'}
                  onChange={(event) => setForm((prev) => ({ ...prev, primaryAgentType: event.target.value }))}
                  className="h-12 rounded-2xl border border-border/80 bg-background/88 px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <option value="codex">Codex</option>
                  <option value="claude-code">Claude Code</option>
                  <option value="custom">Custom</option>
                </select>
                <Input
                  type="number"
                  min={1}
                  max={12}
                  value={form.maxIterations || 3}
                  onChange={(event) =>
                    setForm((prev) => ({ ...prev, maxIterations: Number(event.target.value || 3) }))
                  }
                  placeholder="最大轮次"
                  className="rounded-2xl border-border/80 bg-background/88"
                />
              </div>
              {form.primaryAgentType === 'custom' && (
                <Textarea
                  value={form.primaryAgentCommand || ''}
                  onChange={(event) => setForm((prev) => ({ ...prev, primaryAgentCommand: event.target.value }))}
                  placeholder="自定义命令，支持 {run_dir} / {execution_cwd} / {prompt_file} / {context_file}"
                  className="min-h-[96px] rounded-[1.35rem] border-border/80 bg-background/88"
                />
              )}
              <Input
                value={form.repoPath || ''}
                onChange={(event) => setForm((prev) => ({ ...prev, repoPath: event.target.value }))}
                placeholder="仓库路径，可选"
                className="rounded-2xl border-border/80 bg-background/88"
              />
              <Textarea
                value={form.successCriteria || ''}
                onChange={(event) => setForm((prev) => ({ ...prev, successCriteria: event.target.value }))}
                placeholder="成功标准"
                className="min-h-[88px] rounded-[1.35rem] border-border/80 bg-background/88"
              />
              <div className="rounded-[1.35rem] border border-border/80 bg-background/65 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium">自动检查命令</div>
                  <Button variant="outline" size="sm" onClick={addCheckRow} className="rounded-full">
                    <Plus className="h-4 w-4" />
                    添加检查
                  </Button>
                </div>
                <div className="mt-4 space-y-3">
                  {(form.checkCommands || []).map((item, index) => (
                    <div key={index} className="grid gap-3 lg:grid-cols-[180px_minmax(0,1fr)_88px]">
                      <Input
                        value={item.label}
                        onChange={(event) => updateCheck(index, 'label', event.target.value)}
                        placeholder="检查名称"
                        className="rounded-2xl border-border/80 bg-background/88"
                      />
                      <Input
                        value={item.command}
                        onChange={(event) => updateCheck(index, 'command', event.target.value)}
                        placeholder="命令"
                        className="rounded-2xl border-border/80 bg-background/88"
                      />
                      <Button variant="outline" onClick={() => removeCheckRow(index)} className="rounded-full">
                        删除
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={() => void handleCreateSession()} disabled={isCreating} className="rounded-full">
                  {isCreating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  创建会话
                </Button>
                <Button variant="outline" onClick={() => setIsComposerOpen(false)} className="rounded-full">
                  收起
                </Button>
              </div>
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-4 2xl:grid-cols-[380px_minmax(0,1fr)]">
        <section className="lite-panel rounded-[1.8rem] p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-2xl font-semibold">会话列表</h3>
              <p className="mt-2 text-sm text-muted-foreground">把每次自治尝试都当成可回放、可度量的 session。</p>
            </div>
            {isLoading ? <LoaderCircle className="h-5 w-5 animate-spin text-muted-foreground" /> : null}
          </div>

          <div className="mt-5 space-y-3">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => setSelectedSessionId(session.id)}
                className={cn(
                  'w-full rounded-[1.45rem] border p-4 text-left transition-all',
                  selectedSession?.id === session.id
                    ? 'border-primary/30 bg-primary/10'
                    : 'border-border/80 bg-background/72 hover:bg-background/88'
                )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-display line-clamp-2 text-lg font-semibold">{session.title}</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Badge variant={sessionMeta[session.status][1]}>{sessionMeta[session.status][0]}</Badge>
                      <Badge variant="outline">
                        {session.currentIteration}/{session.maxIterations} 轮
                      </Badge>
                    </div>
                  </div>
                </div>
                <p className="mt-3 line-clamp-2 text-sm leading-6 text-muted-foreground">
                  {session.objective || '还没有单独补充自治目标。'}
                </p>
                <div className="mt-3 text-xs text-muted-foreground">
                  打断 {session.interruptionCount} 次 · 更新于 {fmt(session.updatedAt)}
                </div>
              </button>
            ))}

            {!sessions.length && !isLoading && (
              <div className="rounded-[1.6rem] border border-dashed border-border/80 bg-background/60 p-6 text-sm leading-7 text-muted-foreground">
                当前任务还没有自治会话。可以直接启动 `KAM Dogfood`，也可以自定义检查命令。
              </div>
            )}
          </div>
        </section>

        <section className="lite-panel rounded-[1.8rem] p-5">
          {selectedSession ? (
            <>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="lite-eyebrow">Selected Session</div>
                  <h3 className="font-display mt-3 text-2xl font-semibold">{selectedSession.title}</h3>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Badge variant={sessionMeta[selectedSession.status][1]}>{sessionMeta[selectedSession.status][0]}</Badge>
                    <Badge variant="outline">{selectedSession.primaryAgentType}</Badge>
                    <Badge variant="outline">
                      {selectedSession.currentIteration}/{selectedSession.maxIterations} 轮
                    </Badge>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">
                    {selectedSession.objective || '还没有单独补充自治目标。'}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  {selectedSession.status !== 'running' && selectedSession.status !== 'completed' ? (
                    <Button onClick={() => void handleStartSession(selectedSession.id)} className="rounded-full">
                      <Play className="h-4 w-4" />
                      启动
                    </Button>
                  ) : null}
                  {selectedSession.status === 'running' ? (
                    <Button variant="outline" onClick={() => void handleInterruptSession(selectedSession.id)} className="rounded-full">
                      <PauseCircle className="h-4 w-4" />
                      打断
                    </Button>
                  ) : null}
                  <Button variant="outline" onClick={() => void loadAutonomy()} className="rounded-full">
                    <RefreshCcw className="h-4 w-4" />
                    刷新
                  </Button>
                </div>
              </div>

              <div className="mt-5 grid gap-4 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
                <div className="space-y-4">
                  <div className="rounded-[1.5rem] border border-border/80 bg-background/72 p-4">
                    <div className="text-sm font-medium">成功标准</div>
                    <p className="mt-3 text-sm leading-7 text-muted-foreground">
                      {selectedSession.successCriteria || '未单独配置成功标准。'}
                    </p>
                  </div>
                  <div className="rounded-[1.5rem] border border-border/80 bg-background/72 p-4">
                    <div className="text-sm font-medium">会话配置</div>
                    <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                      <div>主 Agent: {selectedSession.primaryAgentName}</div>
                      <div>仓库路径: {selectedSession.repoPath || '未绑定'}</div>
                      <div>打断次数: {selectedSession.interruptionCount}</div>
                      <div>创建时间: {fmt(selectedSession.createdAt)}</div>
                    </div>
                  </div>
                  <div className="rounded-[1.5rem] border border-border/80 bg-background/72 p-4">
                    <div className="text-sm font-medium">自动检查</div>
                    <div className="mt-3 space-y-3">
                      {(selectedSession.checkCommands || []).map((check) => (
                        <div key={`${check.label}-${check.command}`} className="rounded-[1.2rem] border border-border/70 bg-background/70 p-3">
                          <div className="font-medium">{check.label}</div>
                          <div className="mt-2 break-all text-xs text-muted-foreground">{check.command}</div>
                        </div>
                      ))}
                      {!selectedSession.checkCommands?.length && (
                        <div className="text-sm text-muted-foreground">未配置检查命令，将只根据 run 状态判断是否完成。</div>
                      )}
                    </div>
                  </div>
                </div>

                <div className="rounded-[1.5rem] border border-border/80 bg-background/72 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm font-medium">迭代与检查结果</div>
                    <div className="text-sm text-muted-foreground">{selectedSession.cycles?.length || 0} 条 cycle</div>
                  </div>
                  {selectedSession.cycles?.length ? (
                    <Accordion type="multiple" className="mt-4 rounded-[1.25rem] border border-border/80 bg-background/65 px-4">
                      {selectedSession.cycles.map((cycle) => (
                        <AccordionItem key={cycle.id} value={cycle.id} className="border-border/70">
                          <AccordionTrigger className="hover:no-underline">
                            <div className="min-w-0 text-left">
                              <div className="flex flex-wrap items-center gap-2">
                                <Badge variant={cycle.status === 'passed' ? 'default' : cycle.status === 'failed' ? 'destructive' : 'outline'}>
                                  第 {cycle.iteration} 轮
                                </Badge>
                                <span className="font-medium">{cycle.status}</span>
                                {cycle.workerRun ? <span className="text-xs text-muted-foreground">{cycle.workerRun.agentName}</span> : null}
                              </div>
                              <div className="mt-2 text-xs text-muted-foreground">完成于 {fmt(cycle.completedAt || cycle.createdAt)}</div>
                            </div>
                          </AccordionTrigger>
                          <AccordionContent>
                            <div className="space-y-4">
                              <div className="rounded-[1.2rem] border border-border/80 bg-background/72 p-3">
                                <div className="mb-2 text-sm font-medium">反馈摘要</div>
                                <pre className="lite-console max-h-[12rem] overflow-auto whitespace-pre-wrap">
                                  {cycle.feedbackSummary || '本轮没有额外反馈。'}
                                </pre>
                              </div>
                              <div className="space-y-3">
                                {cycle.checkResults?.map((check, index) => (
                                  <div key={`${check.label}-${index}`} className="rounded-[1.2rem] border border-border/80 bg-background/72 p-3">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <Badge variant={check.passed ? 'default' : 'destructive'}>
                                        {check.passed ? 'PASS' : 'FAIL'}
                                      </Badge>
                                      <span className="font-medium">{check.label}</span>
                                      <span className="text-xs text-muted-foreground">{check.durationMs}ms</span>
                                    </div>
                                    <div className="mt-2 break-all text-xs text-muted-foreground">{check.resolvedCommand}</div>
                                    {(check.stderrPreview || check.stdoutPreview) && (
                                      <pre className="lite-console mt-3 max-h-[10rem] overflow-auto whitespace-pre-wrap">
                                        {check.stderrPreview || check.stdoutPreview}
                                      </pre>
                                    )}
                                  </div>
                                ))}
                                {!cycle.checkResults?.length && (
                                  <div className="text-sm text-muted-foreground">本轮没有额外检查结果。</div>
                                )}
                              </div>
                            </div>
                          </AccordionContent>
                        </AccordionItem>
                      ))}
                    </Accordion>
                  ) : (
                    <div className="mt-4 flex min-h-[16rem] items-center justify-center rounded-[1.35rem] border border-dashed border-border/80 bg-background/60 p-6 text-center text-sm leading-7 text-muted-foreground">
                      会话还没有开始迭代。启动后，这里会记录每一轮 run 与检查反馈。
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="flex min-h-[24rem] items-center justify-center rounded-[1.6rem] border border-dashed border-border/80 bg-background/60 p-6 text-center">
              <div className="max-w-[32rem]">
                <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-background/70 px-4 py-2 text-sm text-muted-foreground">
                  <Bot className="h-4 w-4 text-primary" />
                  先创建一个自治会话
                </div>
                <p className="mt-4 text-sm leading-7 text-muted-foreground">
                  核心指标已经就绪，但当前任务还没有进入自治循环。最短路径是直接启动 `KAM Dogfood`。
                </p>
              </div>
            </div>
          )}
        </section>
      </div>

      {!globalMetrics?.totalSessions && !isLoading ? (
        <div className="rounded-[1.5rem] border border-border/80 bg-background/65 px-5 py-4 text-sm text-muted-foreground">
          <div className="flex items-start gap-3">
            <TriangleAlert className="mt-0.5 h-4 w-4 text-primary" />
            <div>当前还没有形成可统计样本。至少跑一轮自治会话后，三个核心指标才会开始有意义。</div>
          </div>
        </div>
      ) : null}

      {selectedSession?.status === 'completed' ? (
        <div className="rounded-[1.5rem] border border-primary/20 bg-primary/10 px-5 py-4 text-sm text-foreground">
          <div className="flex items-start gap-3">
            <BadgeCheck className="mt-0.5 h-4 w-4 text-primary" />
            <div>
              当前选中的自治会话已经完成。它会被计入“自主完成率”和“完成成功率”。
            </div>
          </div>
        </div>
      ) : null}

      {selectedSession?.status === 'interrupted' ? (
        <div className="rounded-[1.5rem] border border-border/80 bg-background/65 px-5 py-4 text-sm text-muted-foreground">
          <div className="flex items-start gap-3">
            <CircleOff className="mt-0.5 h-4 w-4 text-primary" />
            <div>这次会话已被计入打断率。后续如果要恢复，建议新开一个自治会话而不是继续污染原样本。</div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
