import { useState } from 'react'

import { formatRelativeTime, humanizeSchedule, watcherAutomationLabel, watcherDescription, watcherGlyph, watcherSourceLabel, watcherTargetSummary, watcherTone } from '@/lib/v3-ui'
import type { WatcherEventRecord, WatcherRecord, WatcherUpdatePayload } from '@/types/v3'

type WatcherInspectorProps = {
  watcher: WatcherRecord | null
  events: WatcherEventRecord[]
  mode: 'history' | 'edit'
  loading: boolean
  onModeChange: (mode: 'history' | 'edit') => void
  onSave: (payload: WatcherUpdatePayload) => Promise<void>
  onOpenThread: (threadId: string) => void
}

export function WatcherInspector({ watcher, events, mode, loading, onModeChange, onSave, onOpenThread }: WatcherInspectorProps) {
  const [draftName, setDraftName] = useState(() => watcher?.name ?? '')
  const [draftScheduleValue, setDraftScheduleValue] = useState(() => watcher?.scheduleValue ?? '')
  const [draftAutoActionLevel, setDraftAutoActionLevel] = useState(() => watcher?.autoActionLevel ?? 1)
  const [saving, setSaving] = useState(false)

  if (!watcher) {
    return (
      <aside className="watcher-inspector is-empty">
        <div className="feed-empty">Select a watcher to inspect its history or operating settings.</div>
      </aside>
    )
  }

  const tone = watcherTone(watcher.sourceType)

  return (
    <aside className="watcher-inspector">
      <div className="watcher-inspector-head">
        <div className="watcher-card-leading">
          <div className={`watcher-badge is-${tone}`}>{watcherGlyph(watcher)}</div>
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
        <span className="watcher-automation-pill">{watcherAutomationLabel(watcher.autoActionLevel)}</span>
      </div>

      <div className="watcher-inspector-copy">{watcherDescription(watcher)}</div>

      <div className="watcher-inspector-grid">
        <div>
          <div className="watcher-inspector-label">Target</div>
          <div className="watcher-inspector-value">{watcherTargetSummary(watcher)}</div>
        </div>
        <div>
          <div className="watcher-inspector-label">Last run</div>
          <div className="watcher-inspector-value">{formatRelativeTime(watcher.lastRunAt ?? watcher.createdAt)}</div>
        </div>
        <div>
          <div className="watcher-inspector-label">Mode</div>
          <div className="watcher-inspector-value">{watcherAutomationLabel(watcher.autoActionLevel)}</div>
        </div>
      </div>

      <div className="watcher-inspector-tabs">
        <button type="button" className={`watcher-tab ${mode === 'history' ? 'is-active' : ''}`} onClick={() => onModeChange('history')}>
          History
        </button>
        <button type="button" className={`watcher-tab ${mode === 'edit' ? 'is-active' : ''}`} onClick={() => onModeChange('edit')}>
          Edit
        </button>
      </div>

      {loading ? <div className="feed-empty">Loading watcher…</div> : null}

      {!loading && mode === 'history' ? (
        <div className="watcher-history-list">
          {events.length ? (
            events.map((event) => (
              <article key={event.id} className="watcher-history-card">
                <div className="watcher-history-head">
                  <div>
                    <div className="watcher-history-title">{event.title}</div>
                    <div className="watcher-card-copy">{formatRelativeTime(event.createdAt)}</div>
                  </div>
                  <span className="watcher-history-status">{event.status}</span>
                </div>
                <div className="watcher-card-description">{event.summary}</div>
                {event.actions.length ? (
                  <div className="watcher-chip-row">
                    {event.actions.map((action) => (
                      <span key={`${event.id}-${action.label}`} className="watcher-chip">
                        {action.label}
                      </span>
                    ))}
                  </div>
                ) : null}
                {event.threadId ? (
                  <div className="watcher-actions">
                    <button type="button" className="button-secondary" onClick={() => onOpenThread(event.threadId!)}>
                      Open thread
                    </button>
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <div className="feed-empty">No watcher events yet. Run it once and the timeline will appear here.</div>
          )}
        </div>
      ) : null}

      {!loading && mode === 'edit' ? (
        <form
          className="watcher-edit-form"
          onSubmit={(event) => {
            event.preventDefault()
            if (saving || !draftName.trim() || !draftScheduleValue.trim()) {
              return
            }
            setSaving(true)
            void onSave({
              name: draftName.trim(),
              scheduleValue: draftScheduleValue.trim(),
              autoActionLevel: draftAutoActionLevel,
            }).then(() => {
              onModeChange('history')
            }).finally(() => {
              setSaving(false)
            })
          }}
        >
          <label className="watcher-field">
            <span className="watcher-inspector-label">Name</span>
            <input className="watcher-input" value={draftName} onChange={(event) => setDraftName(event.target.value)} />
          </label>

          <label className="watcher-field">
            <span className="watcher-inspector-label">Frequency</span>
            <input className="watcher-input" value={draftScheduleValue} onChange={(event) => setDraftScheduleValue(event.target.value)} />
          </label>

          <div className="watcher-field">
            <span className="watcher-inspector-label">Automation level</span>
            <div className="watcher-level-row">
              {[1, 2, 3].map((level) => (
                <button
                  key={level}
                  type="button"
                  className={`watcher-level-button ${draftAutoActionLevel === level ? 'is-active' : ''}`}
                  onClick={() => setDraftAutoActionLevel(level)}
                >
                  {watcherAutomationLabel(level)}
                </button>
              ))}
            </div>
          </div>

          <div className="watcher-edit-note">
            Source bindings stay attached to the original AI-generated watcher. Ask AI in a thread if you need to retarget the source itself.
          </div>

          <div className="watcher-actions">
            <button type="submit" className="button-primary" disabled={saving || !draftName.trim() || !draftScheduleValue.trim()}>
              Save changes
            </button>
            <button
              type="button"
              className="button-secondary"
              onClick={() => {
                setDraftName(watcher.name)
                setDraftScheduleValue(watcher.scheduleValue)
                setDraftAutoActionLevel(watcher.autoActionLevel)
                onModeChange('history')
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      ) : null}
    </aside>
  )
}
