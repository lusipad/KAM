import { pauseWatcher, resumeWatcher, runWatcherNow } from '@/api/client'
import { formatRelativeTime, humanizeSchedule, watcherDescription, watcherGlyph, watcherSourceLabel, watcherTone } from '@/lib/v3-ui'
import type { WatcherRecord } from '@/types/v3'

type WatcherListProps = {
  watchers: WatcherRecord[]
  onCreateByConversation: () => void
  onRefresh: () => Promise<void>
}

export function WatcherList({ watchers, onCreateByConversation, onRefresh }: WatcherListProps) {
  return (
    <div className="watcher-list">
      <div className="watcher-column">
        <div className="watcher-header">
          <div className="home-greeting">Watchers · {watchers.filter((watcher) => watcher.status === 'active').length} active</div>
          <div className="home-summary">AI monitors these sources in the background and surfaces events on your Home feed.</div>
        </div>

        {watchers.length ? (
          watchers.map((watcher) => (
            <article key={watcher.id} className="watcher-card">
              <div className="watcher-card-head">
                <div className="watcher-card-leading">
                  <div className={`watcher-badge is-${watcherTone(watcher.sourceType)}`}>{watcherGlyph(watcher)}</div>
                  <div className="watcher-card-title-stack">
                    <div className="watcher-card-title-row">
                      <div className="watcher-card-title">{watcher.name}</div>
                      <span className="watcher-status">{watcher.status}</span>
                    </div>
                    <div className="watcher-card-meta">
                      {watcherSourceLabel(watcher.sourceType)} · {humanizeSchedule(watcher)}
                    </div>
                  </div>
                </div>
              </div>

              <div className="watcher-card-copy">Last: {formatRelativeTime(watcher.lastRunAt ?? watcher.createdAt)}</div>
              <div className="watcher-card-description">{watcherDescription(watcher)}</div>

              <div className="watcher-actions">
                <button
                  type="button"
                  className="button-secondary"
                  onClick={() => {
                    void runWatcherNow(watcher.id).then(() => onRefresh())
                  }}
                >
                  Run now
                </button>
                {watcher.status === 'active' ? (
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      void pauseWatcher(watcher.id).then(() => onRefresh())
                    }}
                  >
                    Pause
                  </button>
                ) : (
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      void resumeWatcher(watcher.id).then(() => onRefresh())
                    }}
                  >
                    Resume
                  </button>
                )}
              </div>
            </article>
          ))
        ) : (
          <div className="feed-empty">No watchers configured yet.</div>
        )}

        <button type="button" className="watcher-create" onClick={onCreateByConversation}>
          Tell AI what to watch to add a new watcher…
        </button>
      </div>
    </div>
  )
}
