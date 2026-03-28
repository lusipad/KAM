import { useEffect, useState } from 'react'

import { activateWatcher, getErrorMessage, getWatcher, getWatcherEvents, pauseWatcher, resumeWatcher, runWatcherNow, updateWatcher } from '@/api/client'
import { WatcherInspector } from '@/features/watcher/WatcherInspector'
import { formatRelativeTime, humanizeSchedule, watcherDescription, watcherGlyph, watcherSourceLabel, watcherStatusLabel, watcherTone } from '@/lib/v3-ui'
import type { WatcherEventRecord, WatcherRecord } from '@/types/v3'

type WatcherListProps = {
  watchers: WatcherRecord[]
  preferredWatcherId: string | null
  onCreateByConversation: () => void
  onRefresh: () => Promise<void>
  onOpenThread: (threadId: string) => void
  onError: (message: string) => void
}

export function WatcherList({ watchers, preferredWatcherId, onCreateByConversation, onRefresh, onOpenThread, onError }: WatcherListProps) {
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
    if (!preferredWatcherId) {
      return
    }
    if (watchers.some((watcher) => watcher.id === preferredWatcherId)) {
      setSelectedWatcherId(preferredWatcherId)
      setInspectorMode('history')
      setLoadingOverride(true)
    }
  }, [preferredWatcherId, watchers])

  useEffect(() => {
    if (!selectedWatcherId && !preferredWatcherId && watchers.length) {
      setSelectedWatcherId(watchers[0].id)
    }
  }, [preferredWatcherId, selectedWatcherId, watchers])

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
      .catch((error) => {
        if (!cancelled) {
          onError(getErrorMessage(error, '加载监控详情失败。'))
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingOverride(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [effectiveSelectedWatcherId, onError])

  async function refreshSelection(nextWatcherId = effectiveSelectedWatcherId) {
    setLoadingOverride(true)
    try {
      await onRefresh()
      if (!nextWatcherId) {
        setInspectorWatcher(null)
        setInspectorEvents([])
        return true
      }
      const [watcher, history] = await Promise.all([getWatcher(nextWatcherId), getWatcherEvents(nextWatcherId)])
      setInspectorWatcher(watcher)
      setInspectorEvents(history.events)
      return true
    } catch (error) {
      onError(getErrorMessage(error, '刷新监控状态失败。'))
      return false
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
            <div className="home-greeting">监控 · {watchers.filter((watcher) => watcher.status === 'active').length} 个运行中</div>
            <div className="home-summary">AI 会在后台持续监控这些来源，只把真正需要你处理的事件推到首页。</div>
          </div>

          {watchers.length ? (
            watchers.map((watcher) => (
              <article key={watcher.id} className={`watcher-card ${effectiveSelectedWatcherId === watcher.id ? 'is-selected' : ''}`}>
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
                          <span className="watcher-status">{watcherStatusLabel(watcher.status)}</span>
                        </div>
                        <div className="watcher-card-meta">
                          {watcherSourceLabel(watcher.sourceType)} · {humanizeSchedule(watcher)}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="watcher-card-copy">最近执行：{formatRelativeTime(watcher.lastRunAt ?? watcher.createdAt)}</div>
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
                    编辑
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => {
                      selectWatcher(watcher.id, 'history')
                    }}
                  >
                    查看历史
                  </button>
                  <button
                    type="button"
                    className={watcher.status === 'draft' ? 'button-primary' : 'button-secondary'}
                    onClick={() => {
                      void (async () => {
                        try {
                          if (watcher.status === 'draft') {
                            await activateWatcher(watcher.id)
                            await refreshSelection(watcher.id)
                            return
                          }
                          setSelectedWatcherId(watcher.id)
                          setInspectorMode('history')
                          await runWatcherNow(watcher.id)
                          await refreshSelection(watcher.id)
                        } catch (error) {
                          onError(getErrorMessage(error, watcher.status === 'draft' ? '启用监控失败。' : '立即执行失败。'))
                        }
                      })()
                    }}
                  >
                    {watcher.status === 'draft' ? '启用监控' : '立即执行'}
                  </button>
                  {watcher.status === 'active' ? (
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => {
                        void (async () => {
                          try {
                            await pauseWatcher(watcher.id)
                            await refreshSelection(watcher.id)
                          } catch (error) {
                            onError(getErrorMessage(error, '暂停监控失败。'))
                          }
                        })()
                      }}
                    >
                      暂停
                    </button>
                  ) : watcher.status === 'paused' ? (
                    <button
                      type="button"
                      className="button-secondary"
                      onClick={() => {
                        void (async () => {
                          try {
                            await resumeWatcher(watcher.id)
                            await refreshSelection(watcher.id)
                          } catch (error) {
                            onError(getErrorMessage(error, '恢复监控失败。'))
                          }
                        })()
                      }}
                    >
                      恢复
                    </button>
                  ) : null}
                </div>
              </article>
            ))
          ) : (
            <div className="feed-empty">还没有配置监控。</div>
          )}

          <button type="button" className="watcher-create" onClick={onCreateByConversation}>
            告诉 AI 你要监控什么，即可新增监控…
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
              return false
            }
            try {
              await updateWatcher(effectiveSelectedWatcherId, payload)
              return await refreshSelection(effectiveSelectedWatcherId)
            } catch (error) {
              onError(getErrorMessage(error, '保存监控失败。'))
              return false
            }
          }}
          onOpenThread={onOpenThread}
        />
      </div>
    </div>
  )
}
