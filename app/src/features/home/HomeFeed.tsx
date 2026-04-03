import { adoptRun, dismissWatcherEvent, executeWatcherAction, getErrorMessage } from '@/api/client'
import { formatRelativeTime, lastLogLine, runStatusLabel, watcherSourceLabel, watcherTone } from '@/lib/v3-ui'
import type { FeedItem, HomeFeedPayload, ThreadSummary } from '@/types/v3'

type HomeFeedProps = {
  feed: HomeFeedPayload | null
  threads: Record<string, ThreadSummary>
  onOpenThread: (threadId: string) => void
  onRefresh: () => Promise<void>
  onError: (message: string) => void
}

function FeedCard({
  item,
  thread,
  compact = false,
  onOpenThread,
  onRefresh,
  onError,
}: {
  item: FeedItem
  thread?: ThreadSummary
  compact?: boolean
  onOpenThread: (threadId: string) => void
  onRefresh: () => Promise<void>
  onError: (message: string) => void
}) {
  if (item.kind === 'watcher_event') {
    const tone = watcherTone(item.watcher?.sourceType)
    const sourceLabel = watcherSourceLabel(item.watcher?.sourceType)

    return (
      <article className="feed-card is-watcher">
        <div className="feed-card-head">
          <div className="feed-card-leading">
            <div className={`feed-icon-badge is-${tone}`}>{tone === 'red' ? 'C' : 'W'}</div>
            <div className="feed-card-title-stack">
              <div className="feed-card-title">{item.title}</div>
              <div className="feed-card-subtle">
                监控：{item.watcher?.name ?? '监控'} · {formatRelativeTime(item.createdAt)}
              </div>
            </div>
          </div>
          <span className="feed-card-badge">{sourceLabel}</span>
        </div>
        <div className="feed-card-copy">{item.summary}</div>
        <div className="feed-actions">
          {item.actions.map((action, index) => (
            <button
              type="button"
              key={`${item.id}-${action.label}`}
              className={index === item.actions.length - 1 ? 'button-primary' : 'button-secondary'}
              onClick={() => {
                void (async () => {
                  try {
                    await executeWatcherAction(item.id, index)
                    await onRefresh()
                  } catch (error) {
                    onError(getErrorMessage(error, '执行监控动作失败。'))
                  }
                })()
              }}
            >
              {action.label}
            </button>
          ))}
          <button
            type="button"
            className="button-secondary"
            onClick={() => {
              void (async () => {
                try {
                  await dismissWatcherEvent(item.id)
                  await onRefresh()
                } catch (error) {
                  onError(getErrorMessage(error, '忽略监控提醒失败。'))
                }
              })()
            }}
          >
            忽略
          </button>
          {item.threadId ? (
            <button type="button" className="button-secondary" onClick={() => onOpenThread(item.threadId!)}>
              打开线程
            </button>
          ) : null}
        </div>
      </article>
    )
  }

  const projectTitle = thread?.project?.title ?? '未归属项目'
  const statusLabel = runStatusLabel(item.status)
  const summary = item.resultSummary || item.task
  const hint = item.status === 'failed' ? lastLogLine(item.rawOutput) : null
  const detailCopy = item.task !== summary ? `任务：${item.task}` : null

  if (compact) {
    return (
      <article className={`feed-card is-recent is-${item.status}`}>
        <div className="feed-card-head">
          <div className="feed-card-title">{summary}</div>
        </div>
        <div className="feed-card-subtle">
          {projectTitle} · {formatRelativeTime(item.createdAt)}
        </div>
      </article>
    )
  }

  return (
    <article className={`feed-card is-${item.status}`}>
      <div className="feed-card-head">
        <div className="feed-card-title-stack">
          <div className="feed-card-title">{summary}</div>
          <div className="feed-card-subtle">
            {projectTitle} · {formatRelativeTime(item.createdAt)}
          </div>
        </div>
        <span className="feed-card-badge">{statusLabel}</span>
      </div>
      {item.status !== 'running' && detailCopy ? <div className="feed-card-copy">{detailCopy}</div> : null}
      {item.status === 'running' ? (
        <>
          <div className="feed-card-copy">{item.rawOutput || item.task}</div>
          <div className="run-progress-bar">
            <span className="run-progress-fill" />
          </div>
        </>
      ) : null}
      {item.status === 'failed' && hint ? <div className="feed-card-hint">可能原因：{hint}</div> : null}
      <div className="feed-actions">
        {item.status === 'passed' && !item.adoptedAt ? (
          <button
            type="button"
            className="button-primary"
            onClick={() => {
              void (async () => {
                try {
                  await adoptRun(item.id)
                  await onRefresh()
                } catch (error) {
                  onError(getErrorMessage(error, '采纳改动失败。'))
                }
              })()
            }}
          >
            采纳改动
          </button>
        ) : null}
        {item.threadId ? (
          <button type="button" className="button-secondary" onClick={() => onOpenThread(item.threadId!)}>
            查看
          </button>
        ) : null}
      </div>
    </article>
  )
}

export function HomeFeed({ feed, threads, onOpenThread, onRefresh, onError }: HomeFeedProps) {
  if (!feed) {
    return <div className="empty-panel">正在加载首页…</div>
  }

  const sections: Array<{ label: string; items: FeedItem[]; compact?: boolean }> = [
    { label: '需要你处理', items: feed.needsAttention },
    { label: '后台进行中', items: feed.running },
    { label: '最近更新', items: feed.recent, compact: true },
  ]

  return (
    <div className="home-feed">
      <div className="home-column">
        <div className="home-hero">
          <div className="home-greeting">{feed.greeting}</div>
          <div className="home-summary">{feed.summary}</div>
        </div>

        {sections.map((section) => (
          <section key={section.label} className="feed-section">
            <div className="section-label">{section.label}</div>
            {section.items.length ? (
              section.items.map((item) => (
                <FeedCard
                  key={`${item.kind}-${item.id}`}
                  item={item}
                  thread={item.threadId ? threads[item.threadId] : undefined}
                  compact={section.compact}
                  onOpenThread={onOpenThread}
                  onRefresh={onRefresh}
                  onError={onError}
                />
              ))
            ) : (
              <div className="feed-empty">现在还没有内容。</div>
            )}
          </section>
        ))}
      </div>
    </div>
  )
}
