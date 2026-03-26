import { GitCompareArrows, CheckCircle2, Clock3, LoaderCircle, Square, XCircle } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ConversationRun } from '@/types/v2';
import { cn } from '@/lib/utils';

function fmtDuration(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  if (value < 1000) return `${value}ms`;
  const seconds = value / 1000;
  return seconds < 60 ? `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function runStatusMeta(status: string) {
  if (status === 'running' || status === 'checking') {
    return { label: status === 'checking' ? 'Checking' : 'Running', toneClass: 'text-sky-500', Icon: LoaderCircle, iconClass: 'animate-spin' };
  }
  if (status === 'passed') return { label: 'Passed', toneClass: 'text-emerald-500', Icon: CheckCircle2, iconClass: '' };
  if (status === 'failed') return { label: 'Failed', toneClass: 'text-rose-500', Icon: XCircle, iconClass: '' };
  if (status === 'cancelled') return { label: 'Cancelled', toneClass: 'text-muted-foreground', Icon: Square, iconClass: '' };
  return { label: 'Pending', toneClass: 'text-muted-foreground', Icon: Clock3, iconClass: '' };
}

function isActiveRun(run?: ConversationRun | null) {
  return !!run && ['pending', 'running', 'checking'].includes(run.status);
}

function artifactPreview(content?: string, maxChars = 90) {
  const normalized = (content || '').trim();
  if (!normalized) return '暂无摘要';
  return normalized.length <= maxChars ? normalized : `${normalized.slice(0, maxChars)}…`;
}

function runDisplayName(run: ConversationRun) {
  const compareLabel = run.metadata?.compareLabel;
  return typeof compareLabel === 'string' && compareLabel.trim() ? compareLabel : `Run ${run.id.slice(0, 6)}`;
}

function summaryText(run: ConversationRun) {
  const summary = run.artifacts?.find((item) => item.type === 'summary')?.content;
  return summary?.trim() || run.error || '';
}

function MetricTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-[1.1rem] border border-border/70 bg-background/70 px-3 py-3">
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className="mt-2 text-lg font-semibold">{value}</div>
    </div>
  );
}

export function RunCompare({
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
    <div className="rounded-[1.25rem] border border-border/70 bg-card/80 px-4 py-4">
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
            <Button
              key={run.id}
              type="button"
              variant="ghost"
              onClick={() => onOpenRun(run.id)}
              className="flex h-auto w-full items-center justify-between gap-3 rounded-[1rem] border border-border/70 bg-background/70 px-3 py-3 text-left transition hover:border-primary/40 hover:bg-primary/5"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{runDisplayName(run)}</div>
                <div className="mt-1 truncate text-xs text-muted-foreground">{artifactPreview(summaryText(run), 90)}</div>
              </div>
              <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                <Icon className={cn('h-3.5 w-3.5', statusMeta.toneClass, statusMeta.iconClass)} />
                <span>{statusMeta.label}</span>
                {run.durationMs ? <span>{fmtDuration(run.durationMs)}</span> : null}
              </div>
            </Button>
          );
        })}
      </div>
    </div>
  );
}
