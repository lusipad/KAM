import {
  CheckCircle2,
  Clock3,
  LoaderCircle,
  Square,
  XCircle,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { collectRunChangeFiles } from '@/components/V2/RunChangePreview';
import type { ConversationRun, ThreadRunArtifactRecord } from '@/types/v2';
import { cn } from '@/lib/utils';

type FileChangeStat = {
  path: string;
  added: number;
  removed: number;
};

function fmtDuration(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  if (value < 1000) return `${value}ms`;
  const seconds = value / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainSeconds}s`;
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object';
}

function artifactDateValue(value?: string | Date) {
  if (!value) return 0;
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
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

function artifactPreview(content?: string, maxChars = 240) {
  const normalized = (content || '').trim();
  if (!normalized) return '暂无内容';
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, maxChars)}…`;
}

function parseCheckResults(content?: string) {
  try {
    const parsed = JSON.parse(content || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function countChangedFiles(changesArtifact?: ThreadRunArtifactRecord) {
  const metadata = (changesArtifact?.metadata || {}) as Record<string, unknown>;
  const changed = metadata.changed;
  if (typeof changed === 'number' && Number.isFinite(changed)) {
    return Math.max(0, changed);
  }
  return Array.isArray(metadata.files) ? metadata.files.length : 0;
}

function summaryText(run?: ConversationRun | null) {
  const artifacts = buildArtifactIndex(run?.artifacts);
  return artifacts.summary?.content?.trim() || run?.error || '暂无摘要';
}

function collectFileChangeStats(patchArtifact?: ThreadRunArtifactRecord) {
  const stats = new Map<string, FileChangeStat>();
  let currentPath = '';

  for (const line of (patchArtifact?.content || '').split('\n')) {
    if (line.startsWith('diff --git ')) {
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
      currentPath = match ? match[2] : '';
      if (currentPath && !stats.has(currentPath)) {
        stats.set(currentPath, { path: currentPath, added: 0, removed: 0 });
      }
      continue;
    }
    if (!currentPath || line.startsWith('+++ ') || line.startsWith('--- ')) continue;
    const current = stats.get(currentPath);
    if (!current) continue;
    if (line.startsWith('+')) current.added += 1;
    if (line.startsWith('-')) current.removed += 1;
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

function runDisplayName(run: ConversationRun) {
  const compareLabel = run.metadata?.compareLabel;
  return typeof compareLabel === 'string' && compareLabel.trim() ? compareLabel : `Run ${run.id.slice(0, 6)}`;
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

export function RunCard({
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
  const adopted = Boolean(run.metadata?.adopted || run.adoptedAt);
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
