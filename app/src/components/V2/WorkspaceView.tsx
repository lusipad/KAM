import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Archive,
  ArrowLeft,
  Bot,
  Brain,
  CheckCircle2,
  Clock3,
  File,
  Folder,
  GitCompareArrows,
  LoaderCircle,
  Paperclip,
  Pin,
  Plus,
  RefreshCcw,
  Save,
  Search,
  Send,
  Settings2,
  Square,
  Trash2,
  XCircle,
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
  ConversationRun,
  DecisionRecord,
  PostThreadMessageResponse,
  ProjectFileTreeRecord,
  ProjectLearningRecord,
  ProjectRecord,
  ProjectResourceRecord,
  ProjectThread,
  ThreadMessageRecord,
  ThreadRunArtifactRecord,
  UserPreferenceRecord,
} from '@/types/v2';
import { SettingsPanel } from '@/components/Settings/SettingsPanel';
import { RunChangePreview, collectRunChangeFiles } from '@/components/V2/RunChangePreview';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Kbd } from '@/components/ui/kbd';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

type WorkspaceMode = 'workspace' | 'memory';
type AgentOption = 'codex' | 'claude-code' | 'custom';

type FileChangeStat = {
  path: string;
  added: number;
  removed: number;
};

const WORKSPACE_STORAGE_KEY = 'kam.v2.workspace';
const NEW_PROJECT_FORM = {
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

function fmtDuration(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  if (value < 1000) return `${value}ms`;
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainSeconds}s`;
}

function isActiveRun(run?: ConversationRun | null) {
  return !!run && ['pending', 'running', 'checking'].includes(run.status);
}

function projectDotClass(status: string) {
  if (status === 'active') return 'bg-emerald-500';
  if (status === 'paused') return 'bg-amber-500';
  if (status === 'done') return 'bg-muted-foreground/70';
  return 'bg-muted-foreground/50';
}

function runTone(status: string) {
  if (status === 'passed') return 'default';
  if (status === 'failed' || status === 'cancelled') return 'destructive';
  if (status === 'running' || status === 'checking') return 'secondary';
  return 'outline';
}

function formatAgentLabel(agent: string) {
  if (agent === 'codex') return 'Codex';
  if (agent === 'claude-code') return 'Claude Code';
  if (agent === 'custom') return 'Custom';
  return agent || 'Agent';
}

function runStatusMeta(status: string) {
  if (status === 'running' || status === 'checking') {
    return {
      label: status === 'checking' ? 'Checking' : 'Running',
      borderClass: 'border-sky-500/30 bg-sky-500/5',
      toneClass: 'text-sky-500',
      Icon: LoaderCircle,
      iconClass: 'animate-spin',
    };
  }

  if (status === 'passed') {
    return {
      label: 'Passed',
      borderClass: 'border-border/70 bg-background/70',
      toneClass: 'text-emerald-500',
      Icon: CheckCircle2,
      iconClass: '',
    };
  }

  if (status === 'failed') {
    return {
      label: 'Failed',
      borderClass: 'border-rose-500/30 bg-rose-500/5',
      toneClass: 'text-rose-500',
      Icon: XCircle,
      iconClass: '',
    };
  }

  if (status === 'cancelled') {
    return {
      label: 'Cancelled',
      borderClass: 'border-border/70 bg-background/70',
      toneClass: 'text-muted-foreground',
      Icon: Square,
      iconClass: '',
    };
  }

  return {
    label: 'Pending',
    borderClass: 'border-border/70 bg-background/70',
    toneClass: 'text-muted-foreground',
    Icon: Clock3,
    iconClass: '',
  };
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

function artifactPreview(content?: string, maxChars = 240) {
  const normalized = (content || '').trim();
  if (!normalized) return '暂无内容';
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, maxChars)}…`;
}

function formatScore(value?: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(3) : null;
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

function countChangedFiles(changesArtifact?: ThreadRunArtifactRecord) {
  const metadata = (changesArtifact?.metadata || {}) as Record<string, unknown>;
  const changed = metadata.changed;
  if (typeof changed === 'number' && Number.isFinite(changed)) {
    return Math.max(0, changed);
  }

  const files = metadata.files;
  if (Array.isArray(files)) {
    return files.length;
  }

  const content = changesArtifact?.content || '';
  const match = content.match(/Changed files:\s*(\d+)/i);
  if (!match) return 0;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0;
}

function summaryText(run?: ConversationRun | null) {
  const artifacts = buildArtifactIndex(run?.artifacts);
  return artifacts.summary?.content?.trim() || run?.error || '暂无摘要';
}

function commandLine(run?: ConversationRun | null) {
  return asString(run?.metadata?.commandLine) || run?.command || '未记录命令';
}

function normalizeDiffPath(rawPath: string) {
  if (rawPath.startsWith('a/') || rawPath.startsWith('b/')) {
    return rawPath.slice(2);
  }
  return rawPath;
}

function collectFileChangeStats(patchArtifact?: ThreadRunArtifactRecord) {
  const stats = new Map<string, FileChangeStat>();
  let currentPath = '';

  for (const line of (patchArtifact?.content || '').split('\n')) {
    if (line.startsWith('diff --git ')) {
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
      currentPath = match ? normalizeDiffPath(match[2]) : '';
      if (currentPath && !stats.has(currentPath)) {
        stats.set(currentPath, {
          path: currentPath,
          added: 0,
          removed: 0,
        });
      }
      continue;
    }

    if (!currentPath) continue;
    if (line.startsWith('+++ ') || line.startsWith('--- ')) continue;

    const current = stats.get(currentPath);
    if (!current) continue;

    if (line.startsWith('+')) {
      current.added += 1;
      continue;
    }

    if (line.startsWith('-')) {
      current.removed += 1;
    }
  }

  return Array.from(stats.values());
}

function tailArtifactLines(content?: string, lines = 3) {
  return (content || '')
    .split('\n')
    .map((line) => line.trimEnd())
    .filter(Boolean)
    .slice(-lines);
}

function runMetrics(run: ConversationRun) {
  const artifactIndex = buildArtifactIndex(run.artifacts);
  const checkResults = parseCheckResults(artifactIndex.check_result?.content);
  return {
    artifactIndex,
    summary: summaryText(run),
    changedFiles: countChangedFiles(artifactIndex.changes),
    fileList: collectRunChangeFiles(artifactIndex.changes, artifactIndex.patch),
    fileStats: collectFileChangeStats(artifactIndex.patch),
    checkResults,
    tailLogs: tailArtifactLines(artifactIndex.stderr?.content || artifactIndex.stdout?.content, 3),
  };
}

function artifactLabel(type: string) {
  const map: Record<string, string> = {
    summary: '摘要',
    check_result: '检查结果',
    feedback: '反馈',
    changes: '变更清单',
    patch: 'Diff',
    stdout: 'Stdout',
    stderr: 'Stderr',
    prompt: 'Prompt',
    context: 'Context',
  };
  return map[type] || type;
}

function runDisplayName(run: ConversationRun) {
  return asString(run.metadata?.compareLabel) || `Run ${run.id.slice(0, 6)}`;
}

function WorkspaceSectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('lite-eyebrow', className)}>{children}</div>;
}

function ConversationEmptyState() {
  return (
    <div className="flex min-h-[340px] flex-col items-center justify-center rounded-[1.75rem] border border-dashed border-border/70 bg-background/40 px-6 text-center">
      <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Bot className="h-5 w-5" />
      </div>
      <div className="mt-5 text-lg font-medium">你在做什么？</div>
      <div className="mt-2 text-sm text-muted-foreground">描述你的目标，我来安排一切。</div>
    </div>
  );
}

function SystemNote({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-[1.35rem] border border-border/70 bg-background/60 px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-sm font-medium">{title}</div>
        {meta}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

function ContextSummaryLine({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn('max-w-[62%] text-right', mono && 'font-mono text-xs')}>{value}</span>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-lg font-semibold">{value}</div>
    </div>
  );
}

function ResourceRow({
  resource,
  onDelete,
}: {
  resource: ProjectResourceRecord;
  onDelete: () => void;
}) {
  const Icon =
    resource.type === 'repo-path' || resource.type === 'path'
      ? Folder
      : resource.type === 'file'
        ? File
        : Paperclip;

  return (
    <div className="flex items-start gap-3 rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
      <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-xl bg-secondary text-muted-foreground">
        <Icon className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <div className="truncate text-sm font-medium">{resource.title || resource.uri}</div>
          {resource.pinned ? <Badge variant="outline">Pinned</Badge> : null}
        </div>
        <div className="mt-1 truncate text-xs text-muted-foreground">{resource.uri}</div>
      </div>
      <Button type="button" size="icon-sm" variant="ghost" onClick={onDelete} aria-label="删除资源">
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}

function MemorySearchBadges({
  item,
}: {
  item: UserPreferenceRecord | DecisionRecord | ProjectLearningRecord;
}) {
  const lexical = formatScore(item.searchScore);
  const semantic = formatScore(item.semanticScore);
  if (!item.matchType && !lexical && !semantic) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {item.matchType ? <Badge variant="outline">{item.matchType}</Badge> : null}
      {lexical ? <Badge variant="outline">lexical {lexical}</Badge> : null}
      {semantic ? <Badge variant="outline">semantic {semantic}</Badge> : null}
    </div>
  );
}

function RunConversationCard({
  run,
  onOpenDetail,
  onAdopt,
  onCancel,
  onRetry,
}: {
  run: ConversationRun;
  onOpenDetail: (runId: string, artifactType?: string) => void;
  onAdopt: (runId: string) => void;
  onCancel: (runId: string) => void;
  onRetry: (runId: string) => void;
}) {
  const statusMeta = runStatusMeta(run.status);
  const metrics = runMetrics(run);
  const passedChecks = metrics.checkResults.filter((item) => Boolean(isRecord(item) && item.passed)).length;
  const checkSummary =
    metrics.checkResults.length > 0 ? `${passedChecks}/${metrics.checkResults.length} checks passed` : null;
  const fileStats = metrics.fileStats.slice(0, 3);
  const fileList = metrics.fileList.slice(0, 3);
  const summary = artifactPreview(metrics.summary, run.status === 'passed' ? 200 : 140);
  const tailLogs = metrics.tailLogs;
  const adopted = Boolean(run.metadata?.adopted);
  const Icon = statusMeta.Icon;

  return (
    <div className={cn('rounded-[1.3rem] border px-4 py-4', statusMeta.borderClass)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold">{runDisplayName(run)}</span>
            <Badge variant="outline">{formatAgentLabel(run.agent)}</Badge>
            {adopted ? <Badge>已采纳</Badge> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <Icon className={cn('h-3.5 w-3.5', statusMeta.toneClass, statusMeta.iconClass)} />
            <span>{statusMeta.label}</span>
            <span>round {run.round}/{run.maxRounds}</span>
            {run.durationMs ? <span>{fmtDuration(run.durationMs)}</span> : null}
          </div>
        </div>
        <Badge variant={runTone(run.status)}>{statusMeta.label}</Badge>
      </div>

      {run.status === 'pending' ? null : (
        <div className="mt-4 text-sm leading-6 text-foreground/90">{summary}</div>
      )}

      {(run.status === 'running' || run.status === 'checking') && tailLogs.length ? (
        <div className="lite-console mt-4 space-y-1">
          {tailLogs.map((line, index) => (
            <div key={`${run.id}-tail-${index}`}>{line}</div>
          ))}
        </div>
      ) : null}

      {run.status === 'passed' && (fileStats.length || fileList.length) ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {fileStats.length
            ? fileStats.map((item) => (
                <Badge key={item.path} variant="outline" className="max-w-full gap-2 px-2 py-1">
                  <span className="truncate">{item.path}</span>
                  <span className="text-emerald-600">+{item.added}</span>
                  <span className="text-rose-600">-{item.removed}</span>
                </Badge>
              ))
            : fileList.map((item) => (
                <Badge key={item.path} variant="outline" className="max-w-full px-2 py-1">
                  <span className="truncate">{item.path}</span>
                </Badge>
              ))}
        </div>
      ) : null}

      {checkSummary ? <div className="mt-4 text-sm text-muted-foreground">{checkSummary}</div> : null}

      <div className="mt-4 flex flex-wrap gap-2">
        {run.status === 'passed' ? (
          <>
            <Button type="button" size="sm" variant="outline" onClick={() => onOpenDetail(run.id, 'patch')}>
              查看 Diff
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onOpenDetail(run.id, 'stdout')}>
              日志
            </Button>
            {!adopted ? (
              <Button type="button" size="sm" onClick={() => onAdopt(run.id)}>
                采纳变更
              </Button>
            ) : null}
            <Button type="button" size="sm" variant="outline" onClick={() => onRetry(run.id)}>
              重试
            </Button>
          </>
        ) : null}

        {(run.status === 'running' || run.status === 'checking') && (
          <>
            <Button type="button" size="sm" variant="outline" onClick={() => onOpenDetail(run.id, 'stdout')}>
              查看完整日志
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onCancel(run.id)}>
              取消
            </Button>
          </>
        )}

        {run.status === 'pending' && (
          <Button type="button" size="sm" variant="outline" onClick={() => onOpenDetail(run.id, 'summary')}>
            查看详情
          </Button>
        )}

        {(run.status === 'failed' || run.status === 'cancelled') && (
          <>
            <Button type="button" size="sm" variant="outline" onClick={() => onOpenDetail(run.id, 'stderr')}>
              查看日志
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={() => onRetry(run.id)}>
              重试
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function CompareGroupInlineCard({
  prompt,
  runs,
  onOpenRun,
}: {
  prompt: string;
  runs: ConversationRun[];
  onOpenRun: (runId: string) => void;
}) {
  const passed = runs.filter((run) => run.status === 'passed').length;
  const failed = runs.filter((run) => run.status === 'failed' || run.status === 'cancelled').length;
  const active = runs.filter((run) => isActiveRun(run)).length;

  return (
    <div className="rounded-[1.2rem] border border-border/70 bg-card/80 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-sm font-medium">
            <GitCompareArrows className="h-4 w-4 text-primary" />
            Compare
          </div>
          <div className="mt-2 text-sm text-foreground/90">{prompt || 'Compare'}</div>
        </div>
        <Badge variant="outline">{runs.length} runs</Badge>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <MetricTile label="Passed" value={passed} />
        <MetricTile label="Failed" value={failed} />
        <MetricTile label="Active" value={active} />
      </div>

      <div className="mt-4 space-y-2">
        {runs.map((run) => {
          const statusMeta = runStatusMeta(run.status);
          const Icon = statusMeta.Icon;
          return (
            <button
              key={run.id}
              type="button"
              onClick={() => onOpenRun(run.id)}
              className="flex w-full items-center justify-between gap-3 rounded-[1rem] border border-border/70 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40 hover:bg-primary/5"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{runDisplayName(run)}</div>
                <div className="mt-1 truncate text-xs text-muted-foreground">{artifactPreview(summaryText(run), 90)}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                <Icon className={cn('h-3.5 w-3.5', statusMeta.toneClass, statusMeta.iconClass)} />
                <span>{statusMeta.label}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

type MemoryScreenProps = {
  selectedProject: ProjectRecord | null;
  selectedProjectId: string | null;
  memoryQuery: string;
  onMemoryQueryChange: (value: string) => void;
  onBack: () => void;
  preferences: UserPreferenceRecord[];
  decisions: DecisionRecord[];
  learnings: ProjectLearningRecord[];
  preferenceForm: { category: string; key: string; value: string };
  decisionForm: { question: string; decision: string; reasoning: string };
  learningForm: { content: string };
  preferenceDrafts: Record<string, string>;
  decisionDrafts: Record<string, { question: string; decision: string; reasoning: string }>;
  learningDrafts: Record<string, string>;
  onPreferenceFormChange: (next: { category: string; key: string; value: string }) => void;
  onDecisionFormChange: (next: { question: string; decision: string; reasoning: string }) => void;
  onLearningFormChange: (next: { content: string }) => void;
  onPreferenceDraftChange: (id: string, value: string) => void;
  onDecisionDraftChange: (id: string, next: { question: string; decision: string; reasoning: string }) => void;
  onLearningDraftChange: (id: string, value: string) => void;
  onCreatePreference: () => void;
  onCreateDecision: () => void;
  onCreateLearning: () => void;
  onSavePreference: (id: string) => void;
  onSaveDecision: (id: string) => void;
  onSaveLearning: (id: string) => void;
  isLoading: boolean;
};

function MemoryScreen({
  selectedProject,
  selectedProjectId,
  memoryQuery,
  onMemoryQueryChange,
  onBack,
  preferences,
  decisions,
  learnings,
  preferenceForm,
  decisionForm,
  learningForm,
  preferenceDrafts,
  decisionDrafts,
  learningDrafts,
  onPreferenceFormChange,
  onDecisionFormChange,
  onLearningFormChange,
  onPreferenceDraftChange,
  onDecisionDraftChange,
  onLearningDraftChange,
  onCreatePreference,
  onCreateDecision,
  onCreateLearning,
  onSavePreference,
  onSaveDecision,
  onSaveLearning,
  isLoading,
}: MemoryScreenProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 px-6 py-5">
        <div className="flex items-center gap-3">
          <Button type="button" variant="ghost" size="icon-sm" onClick={onBack} aria-label="返回工作区">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="font-display text-xl font-semibold">Memory</div>
            <div className="mt-1 text-sm text-muted-foreground">
              {selectedProject ? `当前聚焦：${selectedProject.title}` : '跨项目偏好、决策与经验沉淀'}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant="outline">{preferences.length} Preferences</Badge>
          <Badge variant="outline">{decisions.length} Decisions</Badge>
          <Badge variant="outline">{learnings.length} Learnings</Badge>
        </div>
      </div>

      <div className="border-b border-border/70 px-6 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={memoryQuery}
              onChange={(event) => onMemoryQueryChange(event.target.value)}
              placeholder="搜索偏好、决策与经验..."
              className="pl-9"
            />
          </div>
          <div className="text-sm text-muted-foreground">
            {selectedProject ? '正在查看当前项目的决策与经验，偏好保持全局视图。' : '当前展示全局记忆。'}
          </div>
        </div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="grid gap-4 px-6 py-6 xl:grid-cols-3">
          <section className="lite-panel rounded-[1.5rem] p-4">
            <WorkspaceSectionLabel>PREFERENCES</WorkspaceSectionLabel>
            <div className="mt-4 space-y-3">
              <Input
                value={preferenceForm.category}
                onChange={(event) => onPreferenceFormChange({ ...preferenceForm, category: event.target.value })}
                placeholder="category"
              />
              <Input
                value={preferenceForm.key}
                onChange={(event) => onPreferenceFormChange({ ...preferenceForm, key: event.target.value })}
                placeholder="key"
              />
              <Textarea
                value={preferenceForm.value}
                onChange={(event) => onPreferenceFormChange({ ...preferenceForm, value: event.target.value })}
                placeholder="例如：优先用 pnpm / 回复保持简洁"
                className="min-h-[96px]"
              />
              <Button type="button" className="w-full" onClick={onCreatePreference}>
                记录偏好
              </Button>
            </div>

            <div className="mt-5 space-y-3">
              {preferences.map((item) => (
                <div key={item.id} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
                  <div className="flex items-center gap-2 text-sm">
                    <Badge variant="outline">{item.category}</Badge>
                    <span className="font-medium">{item.key}</span>
                  </div>
                  <MemorySearchBadges item={item} />
                  <Textarea
                    value={preferenceDrafts[item.id] ?? item.value}
                    onChange={(event) => onPreferenceDraftChange(item.id, event.target.value)}
                    className="mt-3 min-h-[88px]"
                  />
                  <Button type="button" size="sm" className="mt-3" onClick={() => onSavePreference(item.id)}>
                    保存
                  </Button>
                </div>
              ))}
              {!preferences.length && !isLoading ? (
                <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                  还没有记录偏好。
                </div>
              ) : null}
            </div>
          </section>

          <section className="lite-panel rounded-[1.5rem] p-4">
            <WorkspaceSectionLabel>DECISIONS</WorkspaceSectionLabel>
            <div className="mt-4 space-y-3">
              <Input
                value={decisionForm.question}
                onChange={(event) => onDecisionFormChange({ ...decisionForm, question: event.target.value })}
                placeholder="问题"
                disabled={!selectedProjectId}
              />
              <Input
                value={decisionForm.decision}
                onChange={(event) => onDecisionFormChange({ ...decisionForm, decision: event.target.value })}
                placeholder="决策"
                disabled={!selectedProjectId}
              />
              <Textarea
                value={decisionForm.reasoning}
                onChange={(event) => onDecisionFormChange({ ...decisionForm, reasoning: event.target.value })}
                placeholder={selectedProjectId ? '为什么这么决定' : '选择项目后可记录决策'}
                className="min-h-[96px]"
                disabled={!selectedProjectId}
              />
              <Button type="button" className="w-full" onClick={onCreateDecision} disabled={!selectedProjectId}>
                记录决策
              </Button>
            </div>

            <div className="mt-5 space-y-3">
              {decisions.map((item) => {
                const draft = decisionDrafts[item.id] || {
                  question: item.question,
                  decision: item.decision,
                  reasoning: item.reasoning || '',
                };
                return (
                  <div key={item.id} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
                    <MemorySearchBadges item={item} />
                    <Input
                      value={draft.question}
                      onChange={(event) => onDecisionDraftChange(item.id, { ...draft, question: event.target.value })}
                      className="mt-3"
                    />
                    <Input
                      value={draft.decision}
                      onChange={(event) => onDecisionDraftChange(item.id, { ...draft, decision: event.target.value })}
                      className="mt-3"
                    />
                    <Textarea
                      value={draft.reasoning}
                      onChange={(event) => onDecisionDraftChange(item.id, { ...draft, reasoning: event.target.value })}
                      className="mt-3 min-h-[88px]"
                    />
                    <Button type="button" size="sm" className="mt-3" onClick={() => onSaveDecision(item.id)}>
                      保存
                    </Button>
                  </div>
                );
              })}
              {!decisions.length && !isLoading ? (
                <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                  还没有记录决策。
                </div>
              ) : null}
            </div>
          </section>

          <section className="lite-panel rounded-[1.5rem] p-4">
            <WorkspaceSectionLabel>LEARNINGS</WorkspaceSectionLabel>
            <div className="mt-4 space-y-3">
              <Textarea
                value={learningForm.content}
                onChange={(event) => onLearningFormChange({ content: event.target.value })}
                placeholder={selectedProjectId ? '记录这次工作沉淀出的经验' : '选择项目后可记录经验'}
                className="min-h-[120px]"
                disabled={!selectedProjectId}
              />
              <Button type="button" className="w-full" onClick={onCreateLearning} disabled={!selectedProjectId}>
                记录经验
              </Button>
            </div>

            <div className="mt-5 space-y-3">
              {learnings.map((item) => (
                <div key={item.id} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
                  <MemorySearchBadges item={item} />
                  <Textarea
                    value={learningDrafts[item.id] ?? item.content}
                    onChange={(event) => onLearningDraftChange(item.id, event.target.value)}
                    className="mt-3 min-h-[96px]"
                  />
                  <Button type="button" size="sm" className="mt-3" onClick={() => onSaveLearning(item.id)}>
                    保存
                  </Button>
                </div>
              ))}
              {!learnings.length && !isLoading ? (
                <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                  还没有记录经验。
                </div>
              ) : null}
            </div>
          </section>
        </div>
      </ScrollArea>
    </div>
  );
}

type ConversationScreenProps = {
  selectedProject: ProjectRecord | null;
  selectedThread: ProjectThread | null;
  messageText: string;
  onMessageTextChange: (value: string) => void;
  agent: AgentOption;
  onAgentChange: (value: AgentOption) => void;
  customCommand: string;
  onCustomCommandChange: (value: string) => void;
  isMutating: boolean;
  isSendingMessage: boolean;
  streamingReplyText: string;
  errorMessage: string | null;
  onSendMessage: () => void;
  onOpenContext: () => void;
  onOpenRunDetail: (runId: string, artifactType?: string) => void;
  onAdoptRun: (runId: string) => void;
  onCancelRun: (runId: string) => void;
  onRetryRun: (runId: string) => void;
  runDetailsById: Record<string, ConversationRun>;
};

function ConversationScreen({
  selectedProject,
  selectedThread,
  messageText,
  onMessageTextChange,
  agent,
  onAgentChange,
  customCommand,
  onCustomCommandChange,
  isMutating,
  isSendingMessage,
  streamingReplyText,
  errorMessage,
  onSendMessage,
  onOpenContext,
  onOpenRunDetail,
  onAdoptRun,
  onCancelRun,
  onRetryRun,
  runDetailsById,
}: ConversationScreenProps) {
  const messages = selectedThread?.messages || [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 px-6 py-5">
        {selectedProject ? (
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>{selectedProject.title}</BreadcrumbItem>
              {selectedThread ? (
                <>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>{selectedThread.title}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              ) : null}
            </BreadcrumbList>
          </Breadcrumb>
        ) : (
          <div className="font-display text-xl font-semibold">KAM</div>
        )}

        {selectedProject ? (
          <Button type="button" variant="outline" size="sm" onClick={onOpenContext}>
            Context
          </Button>
        ) : (
          <div />
        )}
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-5 px-5 py-6">
          {errorMessage ? (
            <div className="rounded-[1.2rem] border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {errorMessage}
            </div>
          ) : null}

          {!messages.length ? <ConversationEmptyState /> : null}

          {messages.map((message) => {
            const runs = (message.runs || []).map((run) => runDetailsById[run.id] || run);
            const systemEventType = asString(message.metadata?.eventType);
            const comparePrompt = asString(message.metadata?.comparePrompt) || message.content.replace(/^并发对比：/, '');

            if (message.role === 'system' && systemEventType) {
              const eventLabelMap: Record<string, string> = {
                'run-created': 'Run Created',
                'compare-created': 'Compare',
                'run-started': 'Running',
                'run-checking': 'Checking',
                'run-retrying': 'Retrying',
                'run-passed': 'Passed',
                'run-failed': 'Failed',
                'run-cancelled': 'Cancelled',
              };

              return (
                <SystemNote
                  key={message.id}
                  title={eventLabelMap[systemEventType] || 'System'}
                  meta={
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      {asString(message.metadata?.agent) ? (
                        <Badge variant="outline">{formatAgentLabel(asString(message.metadata?.agent))}</Badge>
                      ) : null}
                      <span>{fmtTime(message.createdAt)}</span>
                    </div>
                  }
                >
                  <div className="whitespace-pre-wrap text-sm leading-6 text-foreground/90">{message.content}</div>
                  {systemEventType === 'compare-created' && runs.length > 1 ? (
                    <div className="mt-4">
                      <CompareGroupInlineCard
                        prompt={comparePrompt}
                        runs={runs}
                        onOpenRun={(runId) => onOpenRunDetail(runId, 'summary')}
                      />
                    </div>
                  ) : null}
                  {runs.length ? (
                    <div className="mt-4 space-y-3">
                      {runs.map((run) => (
                        <RunConversationCard
                          key={run.id}
                          run={run}
                          onOpenDetail={onOpenRunDetail}
                          onAdopt={onAdoptRun}
                          onCancel={onCancelRun}
                          onRetry={onRetryRun}
                        />
                      ))}
                    </div>
                  ) : null}
                </SystemNote>
              );
            }

            if (message.role === 'user') {
              return (
                <div key={message.id} className="flex justify-end">
                  <div className="max-w-[80%] rounded-[1rem] bg-secondary px-4 py-3 text-sm leading-6 text-secondary-foreground">
                    <div className="whitespace-pre-wrap break-words">{message.content}</div>
                    <div className="mt-2 text-[11px] text-muted-foreground">{fmtTime(message.createdAt)}</div>
                  </div>
                </div>
              );
            }

            return (
              <div key={message.id} className="flex gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                  K
                </div>
                <div className="min-w-0 max-w-[85%] flex-1">
                  <div className="whitespace-pre-wrap break-words text-sm leading-7 text-foreground/95">
                    {message.content}
                  </div>
                  <div className="mt-2 text-[11px] text-muted-foreground">{fmtTime(message.createdAt)}</div>
                  {runs.length ? (
                    <div className="mt-4 space-y-3">
                      {runs.map((run) => (
                        <RunConversationCard
                          key={run.id}
                          run={run}
                          onOpenDetail={onOpenRunDetail}
                          onAdopt={onAdoptRun}
                          onCancel={onCancelRun}
                          onRetry={onRetryRun}
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            );
          })}

          {isSendingMessage && streamingReplyText ? (
            <div className="flex gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">
                K
              </div>
              <div className="max-w-[85%] text-sm leading-7 text-foreground/90">
                <div className="whitespace-pre-wrap break-words">{streamingReplyText}</div>
                <div className="mt-2 text-[11px] text-muted-foreground">流式生成中...</div>
              </div>
            </div>
          ) : null}
        </div>
      </ScrollArea>

      <div className="border-t border-border/70 px-5 py-5">
        <div className="mx-auto w-full max-w-4xl rounded-[1.6rem] border border-border/70 bg-background/80 shadow-[0_14px_40px_rgba(15,23,42,0.06)]">
          <Textarea
            value={messageText}
            onChange={(event) => onMessageTextChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Enter') return;
              if (!event.metaKey && !event.ctrlKey) return;
              event.preventDefault();
              if (isMutating || (agent === 'custom' && !customCommand.trim())) return;
              onSendMessage();
            }}
            placeholder="描述你的目标..."
            className="min-h-[160px] resize-none border-0 bg-transparent px-5 py-5 text-sm leading-7 shadow-none focus-visible:ring-0"
            disabled={isMutating}
          />

          {agent === 'custom' ? (
            <div className="px-5 pb-4">
              <Input
                value={customCommand}
                onChange={(event) => onCustomCommandChange(event.target.value)}
                placeholder="输入自定义命令，例如：npm test"
              />
            </div>
          ) : null}

          <Separator />

          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="ghost" size="icon-sm" disabled aria-label="附件">
                <Paperclip className="h-4 w-4" />
              </Button>
              <Select value={agent} onValueChange={(value) => onAgentChange(value as AgentOption)}>
                <SelectTrigger size="sm" className="h-8 min-w-[138px] rounded-full border-none bg-secondary px-3 text-xs shadow-none">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="codex">Codex</SelectItem>
                  <SelectItem value="claude-code">Claude Code</SelectItem>
                  <SelectItem value="custom">Custom</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <Kbd>⌘</Kbd>
                <Kbd>↵</Kbd>
              </div>
              <Button
                type="button"
                size="icon"
                className="rounded-full"
                aria-label={isSendingMessage ? '发送中' : '发送'}
                onClick={onSendMessage}
                disabled={!messageText.trim() || isMutating || (agent === 'custom' && !customCommand.trim())}
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type ContextSheetPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  selectedProject: ProjectRecord | null;
  projectForm: {
    title: string;
    description: string;
    repoPath: string;
    status: string;
    checkCommands: string;
  };
  onProjectFormChange: (next: {
    title: string;
    description: string;
    repoPath: string;
    status: string;
    checkCommands: string;
  }) => void;
  showProjectEditor: boolean;
  onProjectEditorToggle: (open: boolean) => void;
  pinnedResources: ProjectResourceRecord[];
  resourceForm: { type: string; title: string; uri: string; pinned: boolean };
  onResourceFormChange: (next: { type: string; title: string; uri: string; pinned: boolean }) => void;
  showResourceComposer: boolean;
  onResourceComposerToggle: (open: boolean) => void;
  activeRuns: ConversationRun[];
  fileTree: ProjectFileTreeRecord | null;
  fileTreeQuery: string;
  onFileTreeQueryChange: (value: string) => void;
  isFilesLoading: boolean;
  onRefreshFiles: () => void;
  onOpenRun: (runId: string, artifactType?: string) => void;
  onSaveProject: () => void;
  onArchiveProject: () => void;
  onAddResource: () => void;
  onDeleteResource: (resourceId: string) => void;
  onLoadPath: (path: string) => void;
  onPinRepoEntry: (path: string, name: string) => void;
};

function ContextSheetPanel({
  open,
  onOpenChange,
  selectedProject,
  projectForm,
  onProjectFormChange,
  showProjectEditor,
  onProjectEditorToggle,
  pinnedResources,
  resourceForm,
  onResourceFormChange,
  showResourceComposer,
  onResourceComposerToggle,
  activeRuns,
  fileTree,
  fileTreeQuery,
  onFileTreeQueryChange,
  isFilesLoading,
  onRefreshFiles,
  onOpenRun,
  onSaveProject,
  onArchiveProject,
  onAddResource,
  onDeleteResource,
  onLoadPath,
  onPinRepoEntry,
}: ContextSheetPanelProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[380px]">
        <SheetHeader className="border-b border-border/70 px-5 py-5">
          <SheetTitle>{selectedProject?.title || 'Context'}</SheetTitle>
          <SheetDescription>{selectedProject?.repoPath || '当前项目的设置、资源与运行态'}</SheetDescription>
        </SheetHeader>

        {!selectedProject ? (
          <div className="px-5 py-6 text-sm text-muted-foreground">先选中一个项目，再打开 Context。</div>
        ) : (
          <ScrollArea className="min-h-0 flex-1">
            <div className="px-5 py-4">
              <Accordion type="multiple" defaultValue={['settings', 'resources', 'runs', 'files']} className="w-full">
                <AccordionItem value="settings">
                  <AccordionTrigger>SETTINGS</AccordionTrigger>
                  <AccordionContent className="space-y-4">
                    <ContextSummaryLine label="Repo" value={projectForm.repoPath || '未设置'} mono />
                    <ContextSummaryLine label="Status" value={projectForm.status} />
                    <ContextSummaryLine
                      label="Checks"
                      value={splitCommands(projectForm.checkCommands).length ? splitCommands(projectForm.checkCommands).join(', ') : '未设置'}
                    />

                    {!showProjectEditor ? (
                      <Button type="button" variant="outline" size="sm" onClick={() => onProjectEditorToggle(true)}>
                        Edit settings
                      </Button>
                    ) : (
                      <div className="space-y-3 rounded-[1.1rem] border border-border/70 bg-background/70 p-3">
                        <Input value={projectForm.title} onChange={(event) => onProjectFormChange({ ...projectForm, title: event.target.value })} placeholder="项目标题" />
                        <Input value={projectForm.repoPath} onChange={(event) => onProjectFormChange({ ...projectForm, repoPath: event.target.value })} placeholder="仓库路径" />
                        <select
                          value={projectForm.status}
                          onChange={(event) => onProjectFormChange({ ...projectForm, status: event.target.value })}
                          className="h-10 rounded-xl border border-input bg-background px-3 text-sm"
                        >
                          <option value="active">active</option>
                          <option value="paused">paused</option>
                          <option value="done">done</option>
                        </select>
                        <Textarea value={projectForm.description} onChange={(event) => onProjectFormChange({ ...projectForm, description: event.target.value })} placeholder="项目描述" className="min-h-[100px]" />
                        <Textarea value={projectForm.checkCommands} onChange={(event) => onProjectFormChange({ ...projectForm, checkCommands: event.target.value })} placeholder="每行一个检查命令" className="min-h-[100px] font-mono text-xs" />
                        <div className="flex flex-wrap gap-2">
                          <Button type="button" size="sm" onClick={onSaveProject}>
                            <Save className="h-4 w-4" />
                            保存
                          </Button>
                          <Button type="button" size="sm" variant="outline" onClick={() => onProjectEditorToggle(false)}>
                            收起
                          </Button>
                          <Button type="button" size="sm" variant="outline" onClick={onArchiveProject}>
                            <Archive className="h-4 w-4" />
                            归档
                          </Button>
                        </div>
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="resources">
                  <AccordionTrigger>PINNED RESOURCES</AccordionTrigger>
                  <AccordionContent className="space-y-3">
                    {pinnedResources.map((resource) => (
                      <ResourceRow key={resource.id} resource={resource} onDelete={() => onDeleteResource(resource.id)} />
                    ))}
                    {!pinnedResources.length ? (
                      <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                        还没有 pinned resource。
                      </div>
                    ) : null}

                    {!showResourceComposer ? (
                      <Button type="button" size="sm" variant="outline" onClick={() => onResourceComposerToggle(true)}>
                        <Plus className="h-4 w-4" />
                        Add resource
                      </Button>
                    ) : (
                      <div className="space-y-3 rounded-[1.1rem] border border-border/70 bg-background/70 p-3">
                        <Select value={resourceForm.type} onValueChange={(value) => onResourceFormChange({ ...resourceForm, type: value })}>
                          <SelectTrigger className="w-full">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="note">note</SelectItem>
                            <SelectItem value="url">url</SelectItem>
                            <SelectItem value="file">file</SelectItem>
                            <SelectItem value="repo-path">repo-path</SelectItem>
                          </SelectContent>
                        </Select>
                        <Input value={resourceForm.title} onChange={(event) => onResourceFormChange({ ...resourceForm, title: event.target.value })} placeholder="标题（可选）" />
                        <Textarea value={resourceForm.uri} onChange={(event) => onResourceFormChange({ ...resourceForm, uri: event.target.value })} placeholder="URL / 路径 / 备注" className="min-h-[96px]" />
                        <div className="flex flex-wrap gap-2">
                          <Button type="button" size="sm" onClick={onAddResource}>
                            保存资源
                          </Button>
                          <Button type="button" size="sm" variant="outline" onClick={() => onResourceComposerToggle(false)}>
                            取消
                          </Button>
                        </div>
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="runs">
                  <AccordionTrigger>ACTIVE RUNS</AccordionTrigger>
                  <AccordionContent className="space-y-2">
                    {activeRuns.length ? (
                      activeRuns.map((run) => {
                        const statusMeta = runStatusMeta(run.status);
                        const Icon = statusMeta.Icon;
                        return (
                          <button
                            key={run.id}
                            type="button"
                            onClick={() => onOpenRun(run.id, 'summary')}
                            className="flex w-full items-center justify-between gap-3 rounded-[1rem] border border-border/70 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40 hover:bg-primary/5"
                          >
                            <div className="min-w-0">
                              <div className="truncate text-sm font-medium">{runDisplayName(run)}</div>
                              <div className="mt-1 truncate text-xs text-muted-foreground">{formatAgentLabel(run.agent)}</div>
                            </div>
                            <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                              <Icon className={cn('h-3.5 w-3.5', statusMeta.toneClass, statusMeta.iconClass)} />
                              <span>{statusMeta.label}</span>
                            </div>
                          </button>
                        );
                      })
                    ) : (
                      <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                        当前没有活跃 run。
                      </div>
                    )}
                  </AccordionContent>
                </AccordionItem>

                <AccordionItem value="files">
                  <AccordionTrigger>FILE TREE</AccordionTrigger>
                  <AccordionContent className="space-y-3">
                    {!selectedProject.repoPath ? (
                      <div className="rounded-[1.1rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                        当前项目还没有关联仓库路径。
                      </div>
                    ) : (
                      <>
                        <div className="flex gap-2">
                          <Input value={fileTreeQuery} onChange={(event) => onFileTreeQueryChange(event.target.value)} placeholder="搜索文件" />
                          <Button type="button" size="icon-sm" variant="outline" onClick={onRefreshFiles} aria-label="刷新文件树">
                            <RefreshCcw className={cn('h-4 w-4', isFilesLoading && 'animate-spin')} />
                          </Button>
                        </div>
                        {fileTree?.parentPath !== undefined && fileTree?.parentPath !== null ? (
                          <Button type="button" size="sm" variant="ghost" onClick={() => onLoadPath(fileTree.parentPath || '')}>
                            <ArrowLeft className="h-4 w-4" />
                            返回上一级
                          </Button>
                        ) : null}
                        <div className="rounded-[1.1rem] border border-border/70 bg-background/70">
                          <div className="border-b border-border/70 px-3 py-2 text-xs text-muted-foreground">
                            {fileTree?.currentPath || selectedProject.repoPath}
                          </div>
                          <div className="divide-y divide-border/60">
                            {(fileTree?.entries || []).map((entry) => (
                              <div key={entry.path} className="flex items-center gap-3 px-3 py-3">
                                <button
                                  type="button"
                                  className="flex min-w-0 flex-1 items-center gap-3 text-left"
                                  onClick={() => {
                                    if (entry.type === 'dir') {
                                      onLoadPath(entry.path);
                                    }
                                  }}
                                >
                                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
                                    {entry.type === 'dir' ? <Folder className="h-4 w-4" /> : <File className="h-4 w-4" />}
                                  </div>
                                  <div className="min-w-0">
                                    <div className="truncate text-sm">{entry.name}</div>
                                    <div className="truncate text-xs text-muted-foreground">{entry.path}</div>
                                  </div>
                                </button>
                                <Button type="button" size="icon-sm" variant="ghost" onClick={() => onPinRepoEntry(entry.path, entry.name)} aria-label="固定到资源">
                                  <Pin className="h-4 w-4" />
                                </Button>
                              </div>
                            ))}
                            {!fileTree?.entries.length ? (
                              <div className="px-3 py-4 text-sm text-muted-foreground">
                                {isFilesLoading ? '文件树加载中...' : '当前路径没有匹配项。'}
                              </div>
                            ) : null}
                          </div>
                        </div>
                      </>
                    )}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </div>
          </ScrollArea>
        )}
      </SheetContent>
    </Sheet>
  );
}

type RunDetailSheetPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  run: ConversationRun | null;
  isLoading: boolean;
  detailRounds: Array<{ round: number; artifacts: ThreadRunArtifactRecord[]; index: Record<string, ThreadRunArtifactRecord> }>;
  detailRound: number | null;
  onDetailRoundChange: (round: number) => void;
  detailArtifactTypes: string[];
  detailArtifactType: string;
  onDetailArtifactTypeChange: (type: string) => void;
  detailArtifactIndex: Record<string, ThreadRunArtifactRecord>;
  selectedArtifact: ThreadRunArtifactRecord | undefined;
  selectedCheckResults: Record<string, unknown>[];
  detailChangePath: string | null;
  onDetailChangePath: (path: string | null) => void;
  onAdoptRun: (runId: string) => void;
  onCancelRun: (runId: string) => void;
  onRetryRun: (runId: string) => void;
};

function RunDetailSheetPanel({
  open,
  onOpenChange,
  run,
  isLoading,
  detailRounds,
  detailRound,
  onDetailRoundChange,
  detailArtifactTypes,
  detailArtifactType,
  onDetailArtifactTypeChange,
  detailArtifactIndex,
  selectedArtifact,
  selectedCheckResults,
  detailChangePath,
  onDetailChangePath,
  onAdoptRun,
  onCancelRun,
  onRetryRun,
}: RunDetailSheetPanelProps) {
  const statusMeta = run ? runStatusMeta(run.status) : null;
  const Icon = statusMeta?.Icon;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[760px]">
        <SheetHeader className="border-b border-border/70 px-6 py-5">
          <SheetTitle>{run ? runDisplayName(run) : 'Run Detail'}</SheetTitle>
          <SheetDescription>{run ? commandLine(run) : '查看完整日志、diff 与检查结果'}</SheetDescription>
        </SheetHeader>

        <div className="flex min-h-0 flex-1 flex-col">
          {run ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 px-6 py-4">
                <div className="flex flex-wrap items-center gap-2">
                  {Icon ? <Icon className={cn('h-4 w-4', statusMeta?.toneClass, statusMeta?.iconClass)} /> : null}
                  <Badge variant={runTone(run.status)}>{statusMeta?.label}</Badge>
                  <Badge variant="outline">{formatAgentLabel(run.agent)}</Badge>
                  <Badge variant="outline">round {run.round}/{run.maxRounds}</Badge>
                  {run.durationMs ? <Badge variant="outline">{fmtDuration(run.durationMs)}</Badge> : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {run.status === 'passed' && !run.metadata?.adopted ? (
                    <Button type="button" size="sm" onClick={() => onAdoptRun(run.id)}>
                      采纳
                    </Button>
                  ) : null}
                  {(run.status === 'running' || run.status === 'checking') ? (
                    <Button type="button" size="sm" variant="outline" onClick={() => onCancelRun(run.id)}>
                      取消
                    </Button>
                  ) : null}
                  {(run.status === 'passed' || run.status === 'failed' || run.status === 'cancelled') ? (
                    <Button type="button" size="sm" variant="outline" onClick={() => onRetryRun(run.id)}>
                      重试
                    </Button>
                  ) : null}
                </div>
              </div>

              <div className="border-b border-border/70 px-6 py-4">
                <div className="text-sm leading-6 text-foreground/90">{artifactPreview(summaryText(run), 260)}</div>
              </div>

              <div className="border-b border-border/70 px-6 py-4">
                {detailRounds.length ? (
                  <div className="flex flex-wrap gap-2">
                    {detailRounds.map((item) => (
                      <Button
                        key={item.round}
                        type="button"
                        size="sm"
                        variant={detailRound === item.round ? 'default' : 'outline'}
                        onClick={() => onDetailRoundChange(item.round)}
                      >
                        Round {item.round}
                      </Button>
                    ))}
                  </div>
                ) : null}

                {detailArtifactTypes.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {detailArtifactTypes.map((type) => (
                      <Button
                        key={type}
                        type="button"
                        size="sm"
                        variant={detailArtifactType === type ? 'secondary' : 'ghost'}
                        onClick={() => onDetailArtifactTypeChange(type)}
                      >
                        {artifactLabel(type)}
                      </Button>
                    ))}
                  </div>
                ) : null}
              </div>

              <ScrollArea className="min-h-0 flex-1">
                <div className="px-6 py-5">
                  {isLoading ? <div className="text-sm text-muted-foreground">Run 详情加载中...</div> : null}

                  {!isLoading && detailArtifactType === 'check_result' ? (
                    <div className="space-y-3">
                      {selectedCheckResults.length ? (
                        selectedCheckResults.map((item, index) => {
                          const record = isRecord(item) ? item : {};
                          return (
                            <div key={`check-${index}`} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-4 py-4">
                              <div className="flex items-center justify-between gap-3">
                                <div className="text-sm font-medium">{asString(record.command) || `Check ${index + 1}`}</div>
                                <Badge variant={record.passed ? 'default' : 'destructive'}>
                                  {record.passed ? 'Passed' : 'Failed'}
                                </Badge>
                              </div>
                              <pre className="lite-console mt-3 overflow-x-auto whitespace-pre-wrap">
                                {artifactPreview(checkOutputText(record), 2000)}
                              </pre>
                            </div>
                          );
                        })
                      ) : (
                        <div className="text-sm text-muted-foreground">没有检查结果。</div>
                      )}
                    </div>
                  ) : null}

                  {!isLoading && (detailArtifactType === 'patch' || detailArtifactType === 'changes') ? (
                    <RunChangePreview
                      changesArtifact={detailArtifactIndex.changes}
                      patchArtifact={detailArtifactIndex.patch}
                      selectedPath={detailChangePath}
                      onSelectPath={(path) => onDetailChangePath(path)}
                      showSelector
                      className="rounded-[1.2rem] border border-border/70 bg-background/80"
                    />
                  ) : null}

                  {!isLoading &&
                  detailArtifactType !== 'check_result' &&
                  detailArtifactType !== 'patch' &&
                  detailArtifactType !== 'changes' ? (
                    <div className="rounded-[1.2rem] border border-border/70 bg-background/80 px-4 py-4">
                      <div className="mb-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                        <span>{artifactLabel(detailArtifactType)}</span>
                        {selectedArtifact?.truncated ? <span>内容已截断</span> : null}
                      </div>
                      <pre className="overflow-x-auto whitespace-pre-wrap text-sm leading-6 text-foreground/90">
                        {selectedArtifact?.content || '暂无内容'}
                      </pre>
                    </div>
                  ) : null}
                </div>
              </ScrollArea>
            </>
          ) : (
            <div className="px-6 py-6 text-sm text-muted-foreground">先从对话流里选中一个 run。</div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

type ProjectDialogPanelProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  form: {
    title: string;
    description: string;
    repoPath: string;
    checkCommands: string;
  };
  onFormChange: (next: { title: string; description: string; repoPath: string; checkCommands: string }) => void;
  onSubmit: () => void;
  isMutating: boolean;
};

function ProjectDialogPanel({
  open,
  onOpenChange,
  form,
  onFormChange,
  onSubmit,
  isMutating,
}: ProjectDialogPanelProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[620px]">
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>只保留最少信息，后续细节可以在 Context 里补齐。</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <Input value={form.title} onChange={(event) => onFormChange({ ...form, title: event.target.value })} placeholder="项目标题" />
          <Textarea value={form.description} onChange={(event) => onFormChange({ ...form, description: event.target.value })} placeholder="项目描述（可选）" className="min-h-[110px]" />
          <Input value={form.repoPath} onChange={(event) => onFormChange({ ...form, repoPath: event.target.value })} placeholder="仓库路径（可选）" />
          <Textarea value={form.checkCommands} onChange={(event) => onFormChange({ ...form, checkCommands: event.target.value })} placeholder="检查命令，每行一个（可选）" className="min-h-[110px] font-mono text-xs" />
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button type="button" onClick={onSubmit} disabled={!form.title.trim() || isMutating}>
            创建项目
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
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
  const [createProjectForm, setCreateProjectForm] = useState(NEW_PROJECT_FORM);
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

  const activeRuns = useMemo(
    () => (selectedThread?.runs || []).filter((run) => isActiveRun(run) || ['passed', 'failed', 'cancelled'].includes(run.status)),
    [selectedThread],
  );

  const runIdsInThread = useMemo(() => {
    const ids = new Set<string>();
    (selectedThread?.runs || []).forEach((run) => ids.add(run.id));
    (selectedThread?.messages || []).forEach((message) => {
      (message.runs || []).forEach((run) => ids.add(run.id));
    });
    return Array.from(ids);
  }, [selectedThread]);

  const runWatchKey = useMemo(
    () => (selectedThread?.runs || []).map((run) => `${run.id}:${run.status}:${run.round}`).join('|'),
    [selectedThread],
  );

  const selectedRunDetail = useMemo(() => {
    if (!selectedRunId) return null;
    return runDetailsById[selectedRunId] || (selectedThread?.runs || []).find((run) => run.id === selectedRunId) || null;
  }, [selectedRunId, runDetailsById, selectedThread]);

  const detailRounds = useMemo(() => buildArtifactRounds(selectedRunDetail?.artifacts), [selectedRunDetail]);
  const selectedDetailRoundGroup = useMemo(
    () => detailRounds.find((item) => item.round === detailRound) || detailRounds[0] || null,
    [detailRound, detailRounds],
  );
  const detailArtifactIndex = useMemo(() => buildArtifactIndex(selectedDetailRoundGroup?.artifacts), [selectedDetailRoundGroup]);
  const detailArtifactTypes = useMemo(() => sortArtifactTypes(Object.keys(detailArtifactIndex)), [detailArtifactIndex]);
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
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as { thread?: ProjectThread; hasActiveRuns?: boolean };
        if (!payload.thread) return;
        setSelectedThread(payload.thread);
        setThreads((current) => upsertThreadSummary(current, payload.thread!));
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

    (selectedThread.runs || []).forEach((run) => {
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
  }, [selectedThread?.id, selectedThread?.runs, runWatchKey, runIdsInThread]);

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
      setSelectedThread(thread);
      setThreads((current) => upsertThreadSummary(current, thread));
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
      const nextThread = streamThread as unknown as ProjectThread;
      setSelectedThread(nextThread);
      setThreads((current) => upsertThreadSummary(current, nextThread));
    }

    const runs = asRunList(payload.runs);
    if (runs.length) {
      setRunDetailsById((current) => {
        const next = { ...current };
        runs.forEach((run) => {
          next[run.id] = current[run.id] ? { ...current[run.id], ...run } : run;
        });
        return next;
      });
    }
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

  function handleOpenMemoryView() {
    setWorkspaceMode('memory');
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
          setSelectedThread(null);
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

      if (response.runs?.length) {
        setRunDetailsById((current) => {
          const next = { ...current };
          response.runs.forEach((run) => {
            next[run.id] = current[run.id] ? { ...current[run.id], ...run } : run;
          });
          return next;
        });
      }

      if (response.thread) {
        setSelectedThread(response.thread);
        setThreads((current) => upsertThreadSummary(current, response.thread!));
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
      <div className="grid h-full min-h-0 gap-4 lg:grid-cols-[290px_minmax(0,1fr)]">
        <aside className="lite-panel flex h-full min-h-0 flex-col rounded-[1.9rem] p-4 lg:p-5">
          <button
            type="button"
            onClick={() => setWorkspaceMode('workspace')}
            className="flex items-center gap-3 rounded-[1.3rem] px-2 py-2 text-left transition hover:bg-accent/60"
          >
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 font-display text-sm font-semibold text-primary">
              K
            </div>
            <div>
              <div className="font-display text-xl font-semibold">KAM</div>
              <div className="text-xs text-muted-foreground">Workspace</div>
            </div>
          </button>

          <ScrollArea className="mt-6 min-h-0 flex-1 pr-2">
            <WorkspaceSectionLabel>PROJECTS</WorkspaceSectionLabel>
            <div className="mt-3 space-y-2">
              {projects.map((project) => (
                <button
                  key={project.id}
                  type="button"
                  onClick={() => {
                    setWorkspaceMode('workspace');
                    setSelectedProjectId(project.id);
                  }}
                  className={cn(
                    'w-full rounded-[1.2rem] border px-3 py-3 text-left transition',
                    selectedProjectId === project.id
                      ? 'border-primary/40 bg-primary/8 shadow-[0_12px_30px_rgba(202,99,49,0.10)]'
                      : 'border-border/70 bg-background/60 hover:border-primary/30 hover:bg-primary/5',
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={cn('mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full', projectDotClass(project.status))} />
                        <div className="truncate text-sm font-medium">{project.title}</div>
                      </div>
                      <div className="mt-2 text-xs text-muted-foreground">
                        {project.threadCount} thread{project.threadCount === 1 ? '' : 's'}
                      </div>
                    </div>
                    <Badge variant="outline">{project.status}</Badge>
                  </div>
                </button>
              ))}

              {!projects.length && !isLoading ? (
                <div className="rounded-[1.2rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                  No projects yet
                </div>
              ) : null}
            </div>

            {selectedProject ? (
              <>
                <WorkspaceSectionLabel className="mt-7">THREADS</WorkspaceSectionLabel>
                <div className="mt-3 space-y-2">
                  {threads.map((thread) => {
                    const latestRun = thread.latestRun;
                    const secondary = latestRun
                      ? `${formatAgentLabel(latestRun.agent)} · ${runStatusMeta(latestRun.status).label}`
                      : `${thread.messageCount} 条消息`;
                    return (
                      <button
                        key={thread.id}
                        type="button"
                        onClick={() => {
                          setWorkspaceMode('workspace');
                          setSelectedThreadId(thread.id);
                          setSelectedThread((current) => (current?.id === thread.id ? current : null));
                        }}
                        className={cn(
                          'w-full rounded-[1.2rem] border px-3 py-3 text-left transition',
                          selectedThreadId === thread.id
                            ? 'border-primary/40 bg-primary/8'
                            : 'border-border/70 bg-background/60 hover:border-primary/30 hover:bg-primary/5',
                        )}
                      >
                        <div className="truncate text-sm font-medium">{thread.title}</div>
                        <div className="mt-1 truncate text-xs text-muted-foreground">{secondary}</div>
                      </button>
                    );
                  })}

                  {!threads.length ? (
                    <div className="rounded-[1.2rem] border border-dashed border-border/70 px-3 py-4 text-sm text-muted-foreground">
                      No threads yet
                    </div>
                  ) : null}
                </div>
              </>
            ) : null}
          </ScrollArea>

          <Separator className="my-4" />

          <div className="space-y-2">
            <Button type="button" variant="ghost" className="w-full justify-start rounded-[1rem]" onClick={() => setCreateProjectOpen(true)}>
              <Plus className="h-4 w-4" />
              New project
            </Button>
            <Button
              type="button"
              variant={workspaceMode === 'memory' ? 'secondary' : 'ghost'}
              className="w-full justify-start rounded-[1rem]"
              onClick={handleOpenMemoryView}
            >
              <Brain className="h-4 w-4" />
              Memory
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full justify-start rounded-[1rem]"
              onClick={() => setSettingsOpen(true)}
              aria-label="外观设置"
            >
              <Settings2 className="h-4 w-4" />
              外观设置
            </Button>
          </div>
        </aside>

        <section className="lite-panel flex h-full min-h-0 min-w-0 flex-col rounded-[1.9rem]">
          {workspaceMode === 'memory' ? (
            <MemoryScreen
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
            <ConversationScreen
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
      </div>

      <ContextSheetPanel
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

      <RunDetailSheetPanel
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

      <ProjectDialogPanel
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
