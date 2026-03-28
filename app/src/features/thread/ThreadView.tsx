import { useEffect, useMemo, useState } from 'react'

import { activateWatcher, adoptRun, pauseWatcher, resumeWatcher, retryRun, updateWatcher } from '@/api/client'
import { ReviewCommentCard, type ReviewCard } from '@/features/review/ReviewCommentCard'
import { MessageBubble } from '@/features/thread/MessageBubble'
import { MessageInput } from '@/features/thread/MessageInput'
import { RunCard } from '@/features/thread/RunCard'
import { useSendMessage } from '@/hooks/useSendMessage'
import {
  humanizeScheduleValue,
  watcherAutomationLabel,
  watcherDescription,
  watcherSourceLabel,
  watcherStatusLabel,
  watcherTargetSummary,
} from '@/lib/v3-ui'
import type { MessageRecord, ThreadDetail, WatcherRecord } from '@/types/v3'

type ThreadViewProps = {
  thread: ThreadDetail | null
  watchers: Record<string, WatcherRecord>
  loading: boolean
  pendingPrompt: string | null
  onPendingPromptConsumed: () => void
  onOpenWatcher: (watcherId: string) => void
  onRefresh: () => Promise<void>
}

type TimelineItem =
  | { kind: 'message'; createdAt: string; message: MessageRecord }
  | { kind: 'run'; createdAt: string; run: ThreadDetail['runs'][number] }

function mergeTimeline(thread: ThreadDetail) {
  const items: TimelineItem[] = [
    ...thread.messages.map((message) => ({ kind: 'message', createdAt: message.createdAt, message }) as const),
    ...thread.runs.map((run) => ({ kind: 'run', createdAt: run.createdAt, run }) as const),
  ]

  return items.sort((left, right) => new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime())
}

function reviewCardsFromMessage(message: MessageRecord) {
  const cards = message.metadata.cards
  return Array.isArray(cards) ? cards : []
}

type WatcherSnapshot = Partial<WatcherRecord> & {
  id?: string
  name?: string
  sourceType?: string
  scheduleType?: string
  scheduleValue?: string
  autoActionLevel?: number
  status?: WatcherRecord['status']
}

function resolveWatcher(snapshot: WatcherSnapshot | undefined, liveWatcher: WatcherRecord | null): WatcherRecord | null {
  if (liveWatcher) {
    return liveWatcher
  }
  if (!snapshot?.id && !snapshot?.name) {
    return null
  }
  return {
    id: snapshot.id ?? 'draft-watcher',
    projectId: snapshot.projectId ?? '',
    name: snapshot.name ?? '新监控',
    sourceType: snapshot.sourceType ?? 'github_pr',
    config: snapshot.config ?? {},
    scheduleType: snapshot.scheduleType ?? 'interval',
    scheduleValue: snapshot.scheduleValue ?? '15m',
    status: snapshot.status ?? 'draft',
    autoActionLevel: snapshot.autoActionLevel ?? 1,
    lastRunAt: snapshot.lastRunAt ?? null,
    lastState: snapshot.lastState ?? {},
    createdAt: snapshot.createdAt ?? new Date().toISOString(),
  }
}

function WatcherConfigCard({
  snapshot,
  watcher,
  onRefresh,
  onOpenWatcher,
}: {
  snapshot: WatcherSnapshot | undefined
  watcher: WatcherRecord | null
  onRefresh: () => Promise<void>
  onOpenWatcher: (watcherId: string) => void
}) {
  const current = resolveWatcher(snapshot, watcher)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [draftName, setDraftName] = useState(current?.name ?? '')
  const [draftScheduleValue, setDraftScheduleValue] = useState(current?.scheduleValue ?? '')
  const [draftAutoActionLevel, setDraftAutoActionLevel] = useState(current?.autoActionLevel ?? 1)

  useEffect(() => {
    setDraftName(current?.name ?? '')
    setDraftScheduleValue(current?.scheduleValue ?? '')
    setDraftAutoActionLevel(current?.autoActionLevel ?? 1)
    setEditing(false)
  }, [current?.autoActionLevel, current?.id, current?.name, current?.scheduleValue, current?.status])

  if (!current) {
    return null
  }

  const canPersist = Boolean(current.id && current.id !== 'draft-watcher')

  const saveEdit = async () => {
    if (!canPersist || saving || !draftName.trim() || !draftScheduleValue.trim()) {
      return
    }
    setSaving(true)
    try {
      await updateWatcher(current.id, {
        name: draftName.trim(),
        scheduleValue: draftScheduleValue.trim(),
        autoActionLevel: draftAutoActionLevel,
      })
      setEditing(false)
      await onRefresh()
    } finally {
      setSaving(false)
    }
  }

  const runAction = async (action: () => Promise<unknown>) => {
    if (!canPersist || saving) {
      return
    }
    setSaving(true)
    try {
      await action()
      await onRefresh()
    } finally {
      setSaving(false)
    }
  }

  return (
    <article className={`watcher-config-card is-${current.status}`}>
      <div className="watcher-config-head">
        <div>
          <div className="watcher-config-title">{current.name}</div>
          <div className="watcher-config-subtle">
            {watcherSourceLabel(current.sourceType)} · {watcherStatusLabel(current.status)}
          </div>
        </div>
        <span className="watcher-status">{watcherStatusLabel(current.status)}</span>
      </div>

      {!editing ? (
        <>
          <div className="watcher-config-grid">
            <span>来源：{watcherSourceLabel(current.sourceType)}</span>
            <span>频率：{humanizeScheduleValue(current.scheduleValue)}</span>
            <span>目标：{watcherTargetSummary(current)}</span>
            <span>模式：{watcherAutomationLabel(current.autoActionLevel)}</span>
          </div>
          <div className="watcher-config-copy">{watcherDescription(current)}</div>
          <div className="watcher-actions">
            {current.status === 'draft' ? (
              <button
                type="button"
                className="button-primary"
                disabled={!canPersist || saving}
                onClick={() => {
                  void runAction(() => activateWatcher(current.id))
                }}
              >
                启用监控
              </button>
            ) : current.status === 'active' ? (
              <button
                type="button"
                className="button-secondary"
                disabled={!canPersist || saving}
                onClick={() => {
                  void runAction(() => pauseWatcher(current.id))
                }}
              >
                暂停
              </button>
            ) : (
              <button
                type="button"
                className="button-secondary"
                disabled={!canPersist || saving}
                onClick={() => {
                  void runAction(() => resumeWatcher(current.id))
                }}
              >
                恢复
              </button>
            )}
            <button
              type="button"
              className="button-secondary"
              disabled={!canPersist}
              onClick={() => setEditing(true)}
            >
              编辑细节
            </button>
            {canPersist ? (
              <button type="button" className="button-secondary" onClick={() => onOpenWatcher(current.id)}>
                打开监控页
              </button>
            ) : null}
          </div>
        </>
      ) : (
        <div className="watcher-inline-form">
          <label className="watcher-field">
            <span className="watcher-inspector-label">名称</span>
            <input className="watcher-input" value={draftName} onChange={(event) => setDraftName(event.target.value)} />
          </label>

          <label className="watcher-field">
            <span className="watcher-inspector-label">频率</span>
            <input className="watcher-input" value={draftScheduleValue} onChange={(event) => setDraftScheduleValue(event.target.value)} />
          </label>

          <div className="watcher-field">
            <span className="watcher-inspector-label">自动化级别</span>
            <div className="watcher-level-row">
              {[1, 2, 3].map((level) => (
                <button
                  key={`${current.id}-${level}`}
                  type="button"
                  className={`watcher-level-button ${draftAutoActionLevel === level ? 'is-active' : ''}`}
                  onClick={() => setDraftAutoActionLevel(level)}
                >
                  {watcherAutomationLabel(level)}
                </button>
              ))}
            </div>
          </div>

          <div className="watcher-edit-note">监控目标仍来自这段对话。如果要换目标，直接在对话里重新说一遍会更干净。</div>

          <div className="watcher-actions">
            <button
              type="button"
              className="button-primary"
              disabled={saving || !draftName.trim() || !draftScheduleValue.trim()}
              onClick={() => {
                void saveEdit()
              }}
            >
              保存
            </button>
            <button
              type="button"
              className="button-secondary"
              onClick={() => {
                setDraftName(current.name)
                setDraftScheduleValue(current.scheduleValue)
                setDraftAutoActionLevel(current.autoActionLevel)
                setEditing(false)
              }}
            >
              取消
            </button>
          </div>
        </div>
      )}
    </article>
  )
}

function agentLabel(agent: string | null | undefined) {
  if (agent === 'claude-code') {
    return 'Claude Code'
  }
  if (agent === 'codex') {
    return 'Codex'
  }
  if (agent === 'custom') {
    return '自定义 Agent'
  }
  return '自动选择'
}

function composerMeta(thread: ThreadDetail, isSending: boolean) {
  const latestRun = thread.runs.at(-1) ?? null
  if (!latestRun) {
    return {
      toneLabel: '自动选择',
      detailLabel: isSending ? '正在判断本轮任务' : '当前会按任务判断',
    }
  }

  const detailLabel =
    latestRun.status === 'running'
      ? '执行中'
      : latestRun.status === 'pending'
        ? '已排队'
        : latestRun.status === 'passed'
          ? '沿用最近一次执行上下文'
          : latestRun.status === 'failed'
            ? '最近一次执行失败'
            : '自动识别'

  return {
    toneLabel: agentLabel(latestRun.agent),
    detailLabel: isSending ? '正在判断本轮任务' : detailLabel,
  }
}

export function ThreadView({ thread, watchers, loading, pendingPrompt, onPendingPromptConsumed, onOpenWatcher, onRefresh }: ThreadViewProps) {
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState('')
  const timeline = useMemo(() => (thread ? mergeTimeline(thread) : []), [thread])

  const { isSending, send } = useSendMessage(thread?.id ?? null, {
    onDelta: (delta) => {
      setStreaming((current) => current + delta)
    },
    onToolResult: () => {
      void onRefresh()
    },
    onDone: () => {
      setStreaming('')
      setDraft('')
      void onRefresh()
    },
  })

  useEffect(() => {
    if (!thread || !pendingPrompt || isSending) {
      return
    }

    void send(pendingPrompt)
    onPendingPromptConsumed()
  }, [isSending, onPendingPromptConsumed, pendingPrompt, send, thread])

  if (loading) {
    return <div className="empty-panel">正在加载线程…</div>
  }

  if (!thread) {
    return <div className="empty-panel">选择一个线程继续工作。</div>
  }

  const composer = composerMeta(thread, isSending)

  return (
    <div className="thread-view">
      <div className="thread-scroll">
        <div className="thread-column">
          {timeline.map((item) => {
            if (item.kind === 'run') {
              return (
                <RunCard
                  key={item.run.id}
                  run={item.run}
                  onAdopt={(runId) => {
                    void adoptRun(runId).then(() => onRefresh())
                  }}
                  onRetry={(runId) => {
                    void retryRun(runId).then(() => onRefresh())
                  }}
                />
              )
            }

            if (item.message.role === 'system' && item.message.metadata.kind === 'watcher-config') {
              const watcherSnapshot = item.message.metadata.watcher as WatcherSnapshot | undefined
              const liveWatcher = watcherSnapshot?.id ? watchers[watcherSnapshot.id] ?? null : null
              return (
                <WatcherConfigCard
                  key={item.message.id}
                  snapshot={watcherSnapshot}
                  watcher={liveWatcher}
                  onRefresh={onRefresh}
                  onOpenWatcher={onOpenWatcher}
                />
              )
            }

            if (item.message.metadata.kind === 'review-triage') {
              const cards = reviewCardsFromMessage(item.message)
              return (
                <div key={item.message.id} className="review-stack">
                  <div className="assistant-copy">{item.message.content}</div>
                  {cards.map((card) => (
                    <ReviewCommentCard
                      key={String(card.commentId)}
                      card={card as ReviewCard}
                      onDraftAction={(message) => setDraft(message)}
                    />
                  ))}
                </div>
              )
            }

            return <MessageBubble key={item.message.id} message={item.message} />
          })}

          {streaming ? (
            <div className="message-row is-assistant">
              <div className="assistant-copy">{streaming}</div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="thread-composer">
        <div className="thread-column">
          <MessageInput
            value={draft}
            placeholder="继续输入你的要求..."
            isSending={isSending}
            toneLabel={composer.toneLabel}
            detailLabel={composer.detailLabel}
            onChange={setDraft}
            onSubmit={() => {
              void send(draft)
            }}
          />
        </div>
      </div>
    </div>
  )
}
