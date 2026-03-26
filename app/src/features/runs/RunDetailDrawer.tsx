import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { RunChangePreview } from '@/components/V2/RunChangePreview';
import type { ConversationRun, ThreadRunArtifactRecord } from '@/types/v2';

function formatAgentLabel(agent: string) {
  if (agent === 'codex') return 'Codex';
  if (agent === 'claude-code') return 'Claude Code';
  if (agent === 'custom') return 'Custom';
  return agent || 'Agent';
}

function fmtDuration(value?: number | null) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '—';
  if (value < 1000) return `${value}ms`;
  const seconds = value / 1000;
  return seconds < 60 ? `${seconds.toFixed(seconds >= 10 ? 0 : 1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function runTone(status: string) {
  if (status === 'passed') return 'default';
  if (status === 'failed' || status === 'cancelled') return 'destructive';
  if (status === 'running' || status === 'checking') return 'secondary';
  return 'outline';
}

function runStatusMeta(status: string) {
  if (status === 'running' || status === 'checking') return { label: status === 'checking' ? 'Checking' : 'Running', toneClass: 'text-sky-500', iconClass: '' };
  if (status === 'passed') return { label: 'Passed', toneClass: 'text-emerald-500', iconClass: '' };
  if (status === 'failed') return { label: 'Failed', toneClass: 'text-rose-500', iconClass: '' };
  if (status === 'cancelled') return { label: 'Cancelled', toneClass: 'text-muted-foreground', iconClass: '' };
  return { label: 'Pending', toneClass: 'text-muted-foreground', iconClass: '' };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object';
}

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function artifactPreview(content?: string, maxChars = 260) {
  const normalized = (content || '').trim();
  if (!normalized) return '暂无内容';
  return normalized.length <= maxChars ? normalized : `${normalized.slice(0, maxChars)}…`;
}

function summaryText(run?: ConversationRun | null) {
  const summary = run?.artifacts?.find((item) => item.type === 'summary')?.content;
  return summary?.trim() || run?.error || '暂无摘要';
}

function commandLine(run?: ConversationRun | null) {
  const command = run?.metadata?.commandLine;
  return typeof command === 'string' && command.trim() ? command : run?.command || '未记录命令';
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
  const compareLabel = run.metadata?.compareLabel;
  return typeof compareLabel === 'string' && compareLabel.trim() ? compareLabel : `Run ${run.id.slice(0, 6)}`;
}

function checkOutputText(item: Record<string, unknown>) {
  return asString(item.stderrPreview) || asString(item.stdoutPreview) || asString(item.output);
}

export function RunDetailDrawer({
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
}: {
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
}) {
  const statusMeta = run ? runStatusMeta(run.status) : null;

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
                  <Badge variant={runTone(run.status)}>{statusMeta?.label}</Badge>
                  <Badge variant="outline">{formatAgentLabel(run.agent)}</Badge>
                  <Badge variant="outline">round {run.round}/{run.maxRounds}</Badge>
                  {run.durationMs ? <Badge variant="outline">{fmtDuration(run.durationMs)}</Badge> : null}
                </div>
                <div className="flex flex-wrap gap-2">
                  {run.status === 'passed' && !run.metadata?.adopted ? <Button type="button" size="sm" onClick={() => onAdoptRun(run.id)}>采纳</Button> : null}
                  {(run.status === 'running' || run.status === 'checking') ? <Button type="button" size="sm" variant="outline" onClick={() => onCancelRun(run.id)}>取消</Button> : null}
                  {(run.status === 'passed' || run.status === 'failed' || run.status === 'cancelled') ? <Button type="button" size="sm" variant="outline" onClick={() => onRetryRun(run.id)}>重试</Button> : null}
                </div>
              </div>

              <div className="border-b border-border/70 px-6 py-4">
                <div className="text-sm leading-6 text-foreground/90">{artifactPreview(summaryText(run), 260)}</div>
              </div>

              <div className="border-b border-border/70 px-6 py-4">
                {detailRounds.length ? (
                  <div className="flex flex-wrap gap-2">
                    {detailRounds.map((item) => (
                      <Button key={item.round} type="button" size="sm" variant={detailRound === item.round ? 'default' : 'outline'} onClick={() => onDetailRoundChange(item.round)}>
                        Round {item.round}
                      </Button>
                    ))}
                  </div>
                ) : null}

                {detailArtifactTypes.length ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {detailArtifactTypes.map((type) => (
                      <Button key={type} type="button" size="sm" variant={detailArtifactType === type ? 'secondary' : 'ghost'} onClick={() => onDetailArtifactTypeChange(type)}>
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
                      {selectedCheckResults.length ? selectedCheckResults.map((item, index) => {
                        const record = isRecord(item) ? item : {};
                        return (
                          <div key={`check-${index}`} className="rounded-[1.1rem] border border-border/70 bg-background/70 px-4 py-4">
                            <div className="flex items-center justify-between gap-3">
                              <div className="text-sm font-medium">{asString(record.command) || `Check ${index + 1}`}</div>
                              <Badge variant={record.passed ? 'default' : 'destructive'}>
                                {record.passed ? 'Passed' : 'Failed'}
                              </Badge>
                            </div>
                            <pre className="lite-console mt-3 overflow-x-auto whitespace-pre-wrap">{artifactPreview(checkOutputText(record), 2000)}</pre>
                          </div>
                        );
                      }) : <div className="text-sm text-muted-foreground">没有检查结果。</div>}
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

                  {!isLoading && detailArtifactType !== 'check_result' && detailArtifactType !== 'patch' && detailArtifactType !== 'changes' ? (
                    <div className="rounded-[1.2rem] border border-border/70 bg-background/80 px-4 py-4">
                      <div className="mb-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                        <span>{artifactLabel(detailArtifactType)}</span>
                        {selectedArtifact?.truncated ? <span>内容已截断</span> : null}
                      </div>
                      <pre className="overflow-x-auto whitespace-pre-wrap text-sm leading-6 text-foreground/90">{selectedArtifact?.content || '暂无内容'}</pre>
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
