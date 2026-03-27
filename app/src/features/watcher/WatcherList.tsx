import { useEffect, useState } from 'react'

import { getWatcher, getWatcherEvents, pauseWatcher, resumeWatcher, runWatcherNow, updateWatcher } from '@/api/client'
import { WatcherInspector } from '@/features/watcher/WatcherInspector'
import { formatRelativeTime, humanizeSchedule, watcherDescription, watcherGlyph, watcherSourceLabel, watcherTone } from '@/lib/v3-ui'
import type { WatcherEventRecord, WatcherRecord } from '@/types/v3'

type WatcherListProps = {
  watchers: WatcherRecord[]
  onCreateByConversation: () => void
  onRefresh: () => Promise<void>
  onOpenThread: (threadId: string) => void
}

export function WatcherList({ watchers, onCreateByConversation, onRefresh, onOpenThread }: WatcherListProps) {
  const [selectedWatcherId, setSelectedWatcherId] = useState<string | null>(watchers[0]?.id ?? null)
  const [inspectorMode, setInspectorMode] = useState<'history' | 'edit'>('history')
  const [inspectorWatcher, setInspectorWatcher] = useState<WatcherRecord | null>(null)
  const [inspectorEvents, setInspectorEvents] = useState<WatcherEventRecord[]>([])
  const [loadingOverride, setLoadingOverride] = useState(false)
  const effectiveSelectedWatcherId = watchers.find((watcher) => watcher.id === selectedWatcherId)?.id ?? watchers[0]?.id ?? null
  const activeWatcher = inspectorWatcher?.id === effectiveSelectedWatcherId
    ? inspectorWatcher
    : watchers.find((watcher) => watcher.id === effectiveSelectedWatcherId) ?? null
  const activeEvents = inspectorWatcher?.id === effectiveSelectedWatcherId ? inspectorEvents : []
  const loadingInspector = loadingOverride || (effectiveSelectedWatcherId !== null && inspectorWatcher?.id !== effectiveSelectedWatcherId)

  useEffect(() => {
    if (!effectiveSelectedWatcherId) {
      return
    }

    let cancelled = false

    void Promise.all([getWatcher(effectiveSelectedWatcherId), getWatcherEvents(effectiveSelectedWatcherId)])
      .then(([watcher, history]) => {
        if (cancelled) {
          return
        }
        setInspectorWatcher(watcher)
        setInspectorEvents(history.events)
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingOverride(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [effectiveSelectedWatcherId])

  async function refreshSelection(nextWatcherId = effectiveSelectedWatcherId) {
    setLoadingOverride(true)
    try {
      await onRefresh()
      if (!nextWatcherId) {
        setInspectorWatcher(null)
        setInspectorEvents([])
        return
      }
      const [watcher, history] = await Promise.all([getWatcher(nextWatcherId), getWatcherEvents(nextWatcherId)])
      setInspectorWatcher(watcher)
      setInspectorEvents(history.events)
    } finally {
      setLoadingOverride(false)
    }
  }

  function selectWatcher(nextWatcherId: string, mode: 'history' | 'edit') {
    if (effectiveSelectedWatcherId !== nextWatcherId) {
      setLoadingOverride(true)
      setSelectedWatcherId(nextWatcherId)
    }
    setInspectorMode(mode)
  }

  return (
    <div className="watcher-list">
      <div className="watcher-layout">
        <div className="watcher-column">
          <div className="watcher-header">
            <div className="home-greeting">Watchers · {watchers.filter((watcher) => watcher.status === 'active').length} active</div>
            <div className="home-summary">AI monitors these sources in the background and surfaces events on your Home feed.</div>
          </div>

          {watchers.length ? (
            watchers.map((watcher) => (
              <article key={watcher.id} className={`watcher-card ${selectedWatcherId === watcher.id ? 'is-selected' : ''}`}>
                <button
                  type="button"
                  className="watcher-card-tap"
                  onClick={() => {
                    selectWatcher(watcher.id, 'history')
                  }}
                >
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
                </button>

                <div className="watcher-actions">
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      selectWatcher(watcher.id, 'edit')
                    }}
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      selectWatcher(watcher.id, 'history')
                    }}
                  >
                    View history
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      setSelectedWatcherId(watcher.id)
                      setInspectorMode('history')
                      void runWatcherNow(watcher.id).then(() => refreshSelection(watcher.id))
                    }}
                  >
                    Run now
                  </button>
                  {watcher.status === 'active' ? (
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => {
                        void pauseWatcher(watcher.id).then(() => refreshSelection(watcher.id))
                      }}
                    >
                      Pause
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => {
                        void resumeWatcher(watcher.id).then(() => refreshSelection(watcher.id))
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

        <WatcherInspector
          key={activeWatcher ? `${activeWatcher.id}:${activeWatcher.name}:${activeWatcher.scheduleValue}:${activeWatcher.autoActionLevel}` : 'empty'}
          watcher={activeWatcher}
          events={activeEvents}
          mode={inspectorMode}
          loading={loadingInspector}
          onModeChange={setInspectorMode}
          onSave={async (payload) => {
            if (!effectiveSelectedWatcherId) {
              return
            }
            await updateWatcher(effectiveSelectedWatcherId, payload)
            await refreshSelection(effectiveSelectedWatcherId)
          }}
          onOpenThread={onOpenThread}
        />
      </div>
    </div>
  )
}
