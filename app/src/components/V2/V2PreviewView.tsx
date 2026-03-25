import { useEffect, useMemo, useState } from 'react';
import { Bot, FolderKanban, MessageSquare, Plus, RefreshCcw, Send, Sparkles, Square } from 'lucide-react';
import { v2ProjectsApi, v2RunsApi, v2ThreadsApi } from '@/lib/api-v2';
import type { ConversationRun, ProjectRecord, ProjectThread } from '@/types/v2';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

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

export function V2PreviewView() {
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedProject, setSelectedProject] = useState<ProjectRecord | null>(null);
  const [threads, setThreads] = useState<ProjectThread[]>([]);
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [selectedThread, setSelectedThread] = useState<ProjectThread | null>(null);
  const [projectTitle, setProjectTitle] = useState('');
  const [threadTitle, setThreadTitle] = useState('');
  const [messageText, setMessageText] = useState('');
  const [autoRun, setAutoRun] = useState(true);
  const [agent, setAgent] = useState('codex');
  const [customCommand, setCustomCommand] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    void loadProjects();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    void loadProject(selectedProjectId);
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedThreadId) return;
    void loadThread(selectedThreadId);
  }, [selectedThreadId]);

  useEffect(() => {
    const hasActiveRuns = (selectedThread?.runs || []).some((run) => ['pending', 'running', 'checking'].includes(run.status));
    if (!selectedThreadId || !hasActiveRuns) return;
    const timer = window.setInterval(() => {
      void loadThread(selectedThreadId);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [selectedThread, selectedThreadId]);

  const pinnedResources = useMemo(() => selectedProject?.pinnedResources || [], [selectedProject]);
  const activeRuns = useMemo(() => selectedThread?.runs || [], [selectedThread]);

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
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }

  async function loadProject(projectId: string) {
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

  async function handleCreateProject() {
    if (!projectTitle.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      const created = await v2ProjectsApi.create({
        title: projectTitle.trim(),
        description: 'v2 预览项目',
      });
      setProjectTitle('');
      await loadProjects();
      setSelectedProjectId(created.id);
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
      await loadProject(selectedProjectId);
      setSelectedThreadId(created.id);
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  async function handleSendMessage() {
    if (!selectedThreadId || !messageText.trim()) return;
    setIsMutating(true);
    try {
      setErrorMessage(null);
      await v2ThreadsApi.postMessage(selectedThreadId, {
        content: messageText.trim(),
        createRun: autoRun,
        agent,
        command: agent === 'custom' ? customCommand.trim() || undefined : undefined,
        model: agent === 'codex' ? 'gpt-5.4' : undefined,
        reasoningEffort: agent === 'codex' ? 'xhigh' : undefined,
      });
      setMessageText('');
      if (agent === 'custom') setCustomCommand('');
      await loadThread(selectedThreadId);
      if (selectedProjectId) {
        await loadProject(selectedProjectId);
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
      await v2RunsApi.retry(runId);
      if (selectedThreadId) {
        await loadThread(selectedThreadId);
      }
    } catch (error) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsMutating(false);
    }
  }

  return (
    <div className="grid min-h-[calc(100dvh-2rem)] gap-4 xl:grid-cols-[280px_minmax(0,1fr)_340px]">
      <section className="rounded-[1.75rem] border border-border/70 bg-card/70 p-4 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur">
        <div className="flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/12 text-primary">
            <FolderKanban className="h-5 w-5" />
          </div>
          <div>
            <div className="text-sm font-semibold">Projects</div>
            <div className="text-xs text-muted-foreground">v2 持续上下文</div>
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
                <Badge variant="outline">{project.status}</Badge>
              </div>
              <div className="mt-2 text-xs text-muted-foreground">
                {project.threadCount} 个线程 · {project.resourceCount} 个资源
              </div>
            </button>
          ))}
          {!projects.length && !isLoading && <div className="rounded-2xl border border-dashed border-border/60 px-3 py-5 text-sm text-muted-foreground">先创建一个 Project 开始。</div>}
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
                <div className="mt-1 text-xs text-muted-foreground">{thread.messageCount} 条消息 · {fmtTime(thread.updatedAt)}</div>
              </button>
            ))}
            {!!selectedProjectId && !threads.length && <div className="text-xs text-muted-foreground">还没有线程，先新建一个。</div>}
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
              <div className="text-base font-semibold">{selectedThread?.title || 'V2 Preview 对话区'}</div>
              <div className="text-xs text-muted-foreground">
                {selectedProject?.title ? `${selectedProject.title} · ` : ''}Project / Thread / Run 心智模型预览
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Sparkles className="h-4 w-4 text-primary" />
            Codex 默认模型 `gpt-5.4` · `xhigh`
          </div>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
          {errorMessage && <div className="rounded-2xl border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">{errorMessage}</div>}

          {!selectedThread && (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center gap-3 rounded-[1.75rem] border border-dashed border-border/60 bg-background/40 text-center">
              <Bot className="h-8 w-8 text-primary" />
              <div className="text-base font-semibold">先选择 Project / Thread</div>
              <div className="max-w-md text-sm text-muted-foreground">这一版已经切到 v2 心智：Project 管持续上下文，Thread 管连续对话，Run 内联展示在消息流里。</div>
            </div>
          )}

          {selectedThread?.messages?.map((message) => (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[78%] rounded-[1.6rem] px-4 py-3 ${message.role === 'user' ? 'bg-primary text-primary-foreground' : 'border border-border/60 bg-background/70'}`}>
                <div className="text-[11px] uppercase tracking-[0.22em] opacity-70">{message.role}</div>
                <div className="mt-2 whitespace-pre-wrap text-sm leading-6">{message.content}</div>
                <div className="mt-2 text-[11px] opacity-70">{fmtTime(message.createdAt)}</div>
                {!!message.runs?.length && (
                  <div className="mt-3 space-y-2">
                    {message.runs.map((run) => (
                      <RunInlineCard key={run.id} run={run} onAdopt={() => void handleAdoptRun(run.id)} onCancel={() => void handleCancelRun(run.id)} onRetry={() => void handleRetryRun(run.id)} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="border-t border-border/60 px-5 py-4">
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
            <Textarea
              value={messageText}
              onChange={(event) => setMessageText(event.target.value)}
              placeholder="比如：继续昨天的工作，先把 OAuth token refresh 做完。"
              className="min-h-[112px] rounded-[1.3rem]"
              disabled={!selectedThreadId || isMutating}
            />
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
              <Button className="w-full rounded-xl" onClick={() => void handleSendMessage()} disabled={!selectedThreadId || !messageText.trim() || isMutating || (agent === 'custom' && !customCommand.trim())}>
                <Send className="mr-2 h-4 w-4" />
                发送到 Thread
              </Button>
            </div>
          </div>
        </div>
      </section>

      <aside className="rounded-[1.75rem] border border-border/70 bg-card/70 p-4 shadow-[0_18px_48px_rgba(15,23,42,0.08)] backdrop-blur">
        <div>
          <div className="text-sm font-semibold">Context Panel</div>
          <div className="mt-1 text-xs text-muted-foreground">资源、Run 状态与最新上下文</div>
        </div>

        <div className="mt-5 space-y-5">
          <section>
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-sm font-medium">Pinned Resources</div>
              <Badge variant="secondary">{pinnedResources.length}</Badge>
            </div>
            <div className="space-y-2">
              {pinnedResources.map((resource) => (
                <div key={resource.id} className="rounded-2xl border border-border/60 bg-background/60 px-3 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="truncate text-sm font-medium">{resource.title || resource.type}</div>
                    <Badge variant="outline">{resource.type}</Badge>
                  </div>
                  <div className="mt-2 break-all text-xs text-muted-foreground">{resource.uri}</div>
                </div>
              ))}
              {!pinnedResources.length && <div className="text-xs text-muted-foreground">还没有钉住资源。</div>}
            </div>
          </section>

          <section>
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="text-sm font-medium">Thread Runs</div>
              <Badge variant="secondary">{activeRuns.length}</Badge>
            </div>
            <div className="space-y-2">
              {activeRuns.map((run) => (
                <RunInlineCard key={run.id} run={run} onAdopt={() => void handleAdoptRun(run.id)} onCancel={() => void handleCancelRun(run.id)} onRetry={() => void handleRetryRun(run.id)} compact />
              ))}
              {!activeRuns.length && <div className="text-xs text-muted-foreground">发送消息并勾选自动创建 Run 后，这里会出现执行卡片。</div>}
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function RunInlineCard({
  run,
  onAdopt,
  onCancel,
  onRetry,
  compact = false,
}: {
  run: ConversationRun;
  onAdopt: () => void;
  onCancel: () => void;
  onRetry: () => void;
  compact?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-border/60 bg-background/70 px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <div className="text-sm font-medium">{run.agent}</div>
            <Badge variant={runTone(run.status) as never}>{run.status}</Badge>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {run.model || '未指定模型'} · {run.reasoningEffort || 'default'} · round {run.round}/{run.maxRounds}
          </div>
          {!compact && run.artifacts?.length ? (
            <div className="mt-2 text-xs text-muted-foreground">Artifacts: {run.artifacts.map((item) => item.type).join(', ')}</div>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
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
