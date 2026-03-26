import type { ProjectThread } from '@/types/v2';
import { cn } from '@/lib/utils';

function formatAgentLabel(agent: string) {
  if (agent === 'codex') return 'Codex';
  if (agent === 'claude-code') return 'Claude Code';
  if (agent === 'custom') return 'Custom';
  return agent || 'Agent';
}

function runStatusLabel(status: string) {
  if (status === 'running') return 'Running';
  if (status === 'checking') return 'Checking';
  if (status === 'passed') return 'Passed';
  if (status === 'failed') return 'Failed';
  if (status === 'cancelled') return 'Cancelled';
  return 'Pending';
}

export function ThreadList({
  threads,
  selectedThreadId,
  onSelectThread,
}: {
  threads: ProjectThread[];
  selectedThreadId: string | null;
  onSelectThread: (threadId: string) => void;
}) {
  return (
    <section className="mt-7">
      <div className="lite-eyebrow">THREADS</div>
      <div className="mt-3 space-y-2">
        {threads.map((thread) => {
          const latestRun = thread.latestRun;
          const secondary = latestRun
            ? `${formatAgentLabel(latestRun.agent)} · ${runStatusLabel(latestRun.status)}`
            : `${thread.messageCount} 条消息`;

          return (
            <button
              key={thread.id}
              type="button"
              onClick={() => onSelectThread(thread.id)}
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
    </section>
  );
}
