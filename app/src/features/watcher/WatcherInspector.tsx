import { useState } from 'react'

import {
  formatRelativeTime,
  humanizeSchedule,
  watcherAutomationLabel,
  watcherDescription,
  watcherEventStatusLabel,
  watcherGlyph,
  watcherSourceLabel,
  watcherStatusLabel,
  watcherTargetSummary,
  watcherTone,
} from '@/lib/v3-ui'
import type { WatcherEventRecord, WatcherRecord, WatcherUpdatePayload } from '@/types/v3'

type WatcherInspectorProps = {
  watcher: WatcherRecord | null
  events: WatcherEventRecord[]
  mode: 'history' | 'edit'
  loading: boolean
  onModeChange: (mode: 'history' | 'edit') => void
  onSave: (payload: WatcherUpdatePayload) => Promise<boolean>
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
        <div className="feed-empty">选择一个监控，查看历史或调整设置。</div>
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
              <span className="watcher-status">{watcherStatusLabel(watcher.status)}</span>
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
          <div className="watcher-inspector-label">目标</div>
          <div className="watcher-inspector-value">{watcherTargetSummary(watcher)}</div>
        </div>
        <div>
          <div className="watcher-inspector-label">最近执行</div>
          <div className="watcher-inspector-value">{formatRelativeTime(watcher.lastRunAt ?? watcher.createdAt)}</div>
        </div>
        <div>
          <div className="watcher-inspector-label">模式</div>
          <div className="watcher-inspector-value">{watcherAutomationLabel(watcher.autoActionLevel)}</div>
        </div>
      </div>

      <div className="watcher-inspector-tabs">
        <button type="button" className={`watcher-tab ${mode === 'history' ? 'is-active' : ''}`} onClick={() => onModeChange('history')}>
          历史
        </button>
        <button type="button" className={`watcher-tab ${mode === 'edit' ? 'is-active' : ''}`} onClick={() => onModeChange('edit')}>
          编辑
        </button>
      </div>

      {loading ? <div className="feed-empty">正在加载监控…</div> : null}

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
                  <span className="watcher-history-status">{watcherEventStatusLabel(event.status)}</span>
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
                      打开线程
                    </button>
                  </div>
                ) : null}
              </article>
            ))
          ) : (
            <div className="feed-empty">还没有监控事件。先运行一次，这里就会出现时间线。</div>
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
            }).then((saved) => {
              if (saved) {
                onModeChange('history')
              }
            }).finally(() => {
              setSaving(false)
            })
          }}
        >
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
            来源绑定仍附着在原始 AI 生成的监控上；如果要改监控目标，请回到线程里直接告诉 AI。
          </div>

          <div className="watcher-actions">
            <button type="submit" className="button-primary" disabled={saving || !draftName.trim() || !draftScheduleValue.trim()}>
              保存修改
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
              取消
            </button>
          </div>
        </form>
      ) : null}
    </aside>
  )
}
