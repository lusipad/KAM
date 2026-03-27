import { useEffect, useMemo, useState } from 'react'

import { adoptRun, retryRun } from '@/api/client'
import { ReviewCommentCard, type ReviewCard } from '@/features/review/ReviewCommentCard'
import { MessageBubble } from '@/features/thread/MessageBubble'
import { MessageInput } from '@/features/thread/MessageInput'
import { RunCard } from '@/features/thread/RunCard'
import { useSendMessage } from '@/hooks/useSendMessage'
import type { MessageRecord, ThreadDetail } from '@/types/v3'

type ThreadViewProps = {
  thread: ThreadDetail | null
  loading: boolean
  pendingPrompt: string | null
  onPendingPromptConsumed: () => void
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

export function ThreadView({ thread, loading, pendingPrompt, onPendingPromptConsumed, onRefresh }: ThreadViewProps) {
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
    return <div className="empty-panel">Loading thread…</div>
  }

  if (!thread) {
    return <div className="empty-panel">Select a thread to continue.</div>
  }

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
              const watcher = item.message.metadata.watcher as { name?: string; sourceType?: string; scheduleValue?: string } | undefined
              return (
                <article key={item.message.id} className="watcher-config-card">
                  <div className="watcher-config-title">{watcher?.name ?? 'New watcher'}</div>
                  <div className="watcher-config-grid">
                    <span>Source: {watcher?.sourceType ?? 'unknown'}</span>
                    <span>Frequency: {watcher?.scheduleValue ?? '15m'}</span>
                  </div>
                </article>
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
            placeholder="Reply..."
            isSending={isSending}
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
