import { formatRelativeTime, threadDotTone, threadMeta } from '@/lib/v3-ui'
import type { ThreadSummary } from '@/types/v3'

type SidebarProps = {
  threads: ThreadSummary[]
  activeThreadId: string | null
  activeView: 'empty' | 'home' | 'thread' | 'watchers'
  memoryOpen: boolean
  summary: string
  onSelectHome: () => void
  onSelectThread: (threadId: string) => void
  onSelectWatchers: () => void
  onToggleMemory: () => void
}

function groupThreads(threads: ThreadSummary[]) {
  const grouped = new Map<string, ThreadSummary[]>()
  for (const thread of threads) {
    const label = (thread.project?.title ?? 'No project').toUpperCase()
    grouped.set(label, [...(grouped.get(label) ?? []), thread])
  }
  return Array.from(grouped.entries())
}

export function Sidebar({
  threads,
  activeThreadId,
  activeView,
  memoryOpen,
  summary,
  onSelectHome,
  onSelectThread,
  onSelectWatchers,
  onToggleMemory,
}: SidebarProps) {
  return (
    <aside className="kam-sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">K</div>
        <div>
          <div className="brand-name">KAM</div>
          <div className="brand-subtle">Outside brain</div>
        </div>
      </div>

      <button type="button" className={`active-rail ${activeView === 'home' ? 'is-active' : ''}`} onClick={onSelectHome}>
        <span className="status-dot is-amber" />
        <span>{summary || 'No active items'}</span>
      </button>

      <div className="sidebar-scroll">
        {groupThreads(threads).map(([label, groupedThreads]) => (
          <section key={label} className="thread-group">
            <div className="group-label">{label}</div>
            {groupedThreads.map((thread) => (
              <button
                type="button"
                key={thread.id}
                className={`thread-row ${thread.id === activeThreadId && activeView === 'thread' ? 'is-active' : ''}`}
                onClick={() => onSelectThread(thread.id)}
              >
                <span className={`status-dot is-${threadDotTone(thread)}`} />
                <span className="thread-copy">
                  <span className="thread-title">{thread.title}</span>
                  <span className="thread-meta">{threadMeta(thread) || formatRelativeTime(thread.updatedAt)}</span>
                </span>
              </button>
            ))}
          </section>
        ))}
      </div>

      <div className="sidebar-footer">
        <button type="button" className={`footer-tab ${activeView === 'home' ? 'is-active' : ''}`} onClick={onSelectHome}>
          Home
        </button>
        <button type="button" className={`footer-tab ${activeView === 'watchers' ? 'is-active' : ''}`} onClick={onSelectWatchers}>
          Watchers
        </button>
        <button type="button" className={`footer-tab is-wide ${memoryOpen ? 'is-active' : ''}`} onClick={onToggleMemory}>
          Memory
        </button>
      </div>
    </aside>
  )
}
