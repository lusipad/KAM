import { useMemo } from 'react'

import { MessageInput } from '@/features/thread/MessageInput'
import { RunCard } from '@/features/thread/RunCard'
import { formatRelativeTime } from '@/lib/v3-ui'
import type { RunRecord, TaskDetail } from '@/types/v3'

type TaskWorkbenchProps = {
  task: TaskDetail | null
  loading: boolean
  runPrompt: string
  runAgent: 'codex' | 'claude-code'
  refDraft: { kind: string; label: string; value: string }
  snapshotFocus: string
  selectedRunId: string | null
  creatingRun: boolean
  addingRef: boolean
  creatingSnapshot: boolean
  creatingCompare: boolean
  onRunPromptChange: (value: string) => void
  onRunAgentChange: (agent: 'codex' | 'claude-code') => void
  onCreateRun: () => void
  onRefDraftChange: (draft: { kind: string; label: string; value: string }) => void
  onAddRef: () => void
  onDeleteRef: (refId: string) => void
  onSnapshotFocusChange: (value: string) => void
  onCreateSnapshot: () => void
  onCreateCompare: () => void
  onSelectRun: (runId: string) => void
  onAdoptRun: (runId: string) => void
  onRetryRun: (runId: string) => void
}

function latestRunLabel(run: RunRecord | null) {
  if (!run) {
    return '还没有 run'
  }
  return `${run.agent} · ${run.status} · ${formatRelativeTime(run.createdAt)}`
}

export function TaskWorkbench({
  task,
  loading,
  runPrompt,
  runAgent,
  refDraft,
  snapshotFocus,
  selectedRunId,
  creatingRun,
  addingRef,
  creatingSnapshot,
  creatingCompare,
  onRunPromptChange,
  onRunAgentChange,
  onCreateRun,
  onRefDraftChange,
  onAddRef,
  onDeleteRef,
  onSnapshotFocusChange,
  onCreateSnapshot,
  onCreateCompare,
  onSelectRun,
  onAdoptRun,
  onRetryRun,
}: TaskWorkbenchProps) {
  const selectedRun = useMemo(
    () => task?.runs.find((run) => run.id === selectedRunId) ?? task?.runs.at(-1) ?? null,
    [selectedRunId, task],
  )

  if (loading) {
    return <div className="empty-panel">正在加载任务…</div>
  }

  if (!task) {
    return (
      <div className="empty-state">
        <div className="empty-icon">T</div>
        <div className="empty-title">Task-First Harness</div>
        <div className="empty-copy">先从左侧创建一个任务，再挂 refs、生成 snapshot、启动 runs。</div>
      </div>
    )
  }

  return (
    <div className="task-workbench">
      <div className="task-scroll">
        <div className="thread-column">
          <section className="feed-card task-hero-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">{task.title}</div>
                <div className="feed-card-subtle">
                  {task.description || '当前任务还没有补充描述。'}
                </div>
              </div>
              <span className="feed-card-badge">{task.priority}</span>
            </div>
            <div className="task-chip-row">
              <span className="file-chip">状态 · {task.status}</span>
              {task.repoPath ? <span className="file-chip">Repo · {task.repoPath}</span> : null}
              {task.labels.map((label) => (
                <span key={label} className="file-chip">
                  {label}
                </span>
              ))}
            </div>
          </section>

          <section className="feed-card">
            <div className="feed-card-title">Refs</div>
            <div className="task-inline-form">
              <input
                className="watcher-input"
                value={refDraft.kind}
                onChange={(event) => onRefDraftChange({ ...refDraft, kind: event.target.value })}
                placeholder="kind"
              />
              <input
                className="watcher-input"
                value={refDraft.label}
                onChange={(event) => onRefDraftChange({ ...refDraft, label: event.target.value })}
                placeholder="label"
              />
              <input
                className="watcher-input"
                value={refDraft.value}
                onChange={(event) => onRefDraftChange({ ...refDraft, value: event.target.value })}
                placeholder="value"
              />
              <button type="button" className="button-primary" disabled={addingRef} onClick={onAddRef}>
                添加引用
              </button>
            </div>
            <div className="task-list">
              {task.refs.length ? (
                task.refs.map((ref) => (
                  <article key={ref.id} className="task-list-row">
                    <div className="task-list-copy">
                      <strong>
                        [{ref.kind}] {ref.label}
                      </strong>
                      <span>{ref.value}</span>
                    </div>
                    <button type="button" className="button-secondary" onClick={() => onDeleteRef(ref.id)}>
                      删除
                    </button>
                  </article>
                ))
              ) : (
                <div className="feed-empty">还没有 refs。</div>
              )}
            </div>
          </section>

          <section className="feed-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">Context Snapshot</div>
                <div className="feed-card-subtle">把当前任务和 refs 收敛成可执行上下文。</div>
              </div>
              <button type="button" className="button-primary" disabled={creatingSnapshot} onClick={onCreateSnapshot}>
                生成快照
              </button>
            </div>
            <input
              className="watcher-input"
              value={snapshotFocus}
              onChange={(event) => onSnapshotFocusChange(event.target.value)}
              placeholder="可选 focus，例如：先切前端主入口"
            />
            <div className="task-list">
              {task.snapshots.length ? (
                task.snapshots
                  .slice()
                  .reverse()
                  .map((snapshot) => (
                    <article key={snapshot.id} className="task-list-row">
                      <div className="task-list-copy">
                        <strong>{snapshot.summary}</strong>
                        <span>{snapshot.focus || formatRelativeTime(snapshot.createdAt)}</span>
                      </div>
                    </article>
                  ))
              ) : (
                <div className="feed-empty">还没有 snapshot。</div>
              )}
            </div>
          </section>

          <section className="feed-card">
            <div className="feed-card-head">
              <div className="feed-card-title-stack">
                <div className="feed-card-title">Runs</div>
                <div className="feed-card-subtle">{latestRunLabel(selectedRun)}</div>
              </div>
              <button
                type="button"
                className="button-secondary"
                disabled={task.runs.length < 2 || creatingCompare}
                onClick={onCreateCompare}
              >
                对比最近两个 Run
              </button>
            </div>

            <div className="task-agent-row">
              <button
                type="button"
                className={`watcher-level-button ${runAgent === 'codex' ? 'is-active' : ''}`}
                onClick={() => onRunAgentChange('codex')}
              >
                Codex
              </button>
              <button
                type="button"
                className={`watcher-level-button ${runAgent === 'claude-code' ? 'is-active' : ''}`}
                onClick={() => onRunAgentChange('claude-code')}
              >
                Claude Code
              </button>
            </div>

            <MessageInput
              value={runPrompt}
              placeholder="输入这轮要执行的任务..."
              isSending={creatingRun}
              toneLabel={runAgent === 'codex' ? 'Codex' : 'Claude Code'}
              detailLabel="当前会把任务发给选中的 agent"
              onChange={onRunPromptChange}
              onSubmit={onCreateRun}
            />

            <div className="task-run-stack">
              {task.runs.length ? (
                task.runs
                  .slice()
                  .reverse()
                  .map((run) => (
                    <div key={run.id} className={`task-run-item ${run.id === selectedRun?.id ? 'is-selected' : ''}`}>
                      <button type="button" className="task-run-select" onClick={() => onSelectRun(run.id)}>
                        选中产物
                      </button>
                      <RunCard run={run} onAdopt={onAdoptRun} onRetry={onRetryRun} />
                    </div>
                  ))
              ) : (
                <div className="feed-empty">还没有 runs。</div>
              )}
            </div>
          </section>

          <section className="feed-card">
            <div className="feed-card-title">Compare</div>
            <div className="task-list">
              {task.reviews.length ? (
                task.reviews
                  .slice()
                  .reverse()
                  .map((review) => (
                    <article key={review.id} className="task-list-row">
                      <div className="task-list-copy">
                        <strong>{review.title}</strong>
                        <span>{review.summary || '暂无摘要'}</span>
                      </div>
                    </article>
                  ))
              ) : (
                <div className="feed-empty">还没有 compare。</div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
