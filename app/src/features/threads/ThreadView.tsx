import { Bot, Paperclip, Send } from 'lucide-react';
import type { ReactNode } from 'react';

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Kbd } from '@/components/ui/kbd';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { RunCard } from '@/features/runs/RunCard';
import { RunCompare } from '@/features/runs/RunCompare';
import type { ConversationRun, ProjectRecord, ProjectThread } from '@/types/v2';
import { cn } from '@/lib/utils';

export type AgentOption = 'codex' | 'claude-code' | 'custom';

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

function formatAgentLabel(agent: string) {
  if (agent === 'codex') return 'Codex';
  if (agent === 'claude-code') return 'Claude Code';
  if (agent === 'custom') return 'Custom';
  return agent || 'Agent';
}

function asString(value: unknown) {
  return typeof value === 'string' ? value : '';
}

function ConversationEmptyState() {
  return (
    <div className="flex min-h-[220px] flex-col items-center justify-center rounded-[1.9rem] border border-dashed border-border/70 bg-background/40 px-6 text-center md:min-h-[340px]">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
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

export function ThreadView({
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
}: {
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
}) {
  const messages = selectedThread?.messages || [];
  const isThreadEmpty = !messages.length && !streamingReplyText;

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
                'run-created': 'Run 已创建',
                'compare-created': '对比任务',
                'run-started': '执行中',
                'run-checking': '检查中',
                'run-retrying': '重试中',
                'run-passed': '已完成',
                'run-failed': '失败',
                'run-cancelled': '已取消',
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
                      <RunCompare
                        prompt={comparePrompt}
                        runs={runs}
                        onOpenRun={(runId) => onOpenRunDetail(runId, 'summary')}
                      />
                    </div>
                  ) : null}
                  {runs.length ? (
                    <div className="mt-4 space-y-3">
                      {runs.map((run) => (
                        <RunCard
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
                        <RunCard
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

      <div className="border-t border-border/70 px-4 py-4 lg:px-5 lg:py-4">
        <div className="mx-auto w-full max-w-4xl rounded-[1.75rem] border border-border/70 bg-background/85 shadow-[0_18px_48px_rgba(15,23,42,0.08)]">
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
            className={cn(
              'max-h-[32vh] resize-none overflow-y-auto border-0 bg-transparent px-5 py-4 text-sm leading-6 shadow-none focus-visible:ring-0',
              isThreadEmpty ? 'min-h-[104px] md:min-h-[112px]' : 'min-h-[88px] md:min-h-[96px]',
            )}
            disabled={isMutating}
          />

          {agent === 'custom' ? (
            <div className="px-5 pb-3">
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
              <div className="flex items-center gap-2 rounded-full bg-secondary px-2 py-1">
                <Bot className="h-3.5 w-3.5 text-muted-foreground" />
                <Select value={agent} onValueChange={(value) => onAgentChange(value as AgentOption)}>
                  <SelectTrigger size="sm" className="h-7 min-w-[126px] rounded-full border-none bg-transparent px-2 text-xs shadow-none">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="codex">Codex</SelectItem>
                    <SelectItem value="claude-code">Claude Code</SelectItem>
                    <SelectItem value="custom">Custom</SelectItem>
                  </SelectContent>
                </Select>
              </div>
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
