import { useState } from 'react'

import { codeFiles, formatDuration, lastLogLine, runStatusLabel, runTone } from '@/lib/ui'
import type { RunRecord } from '@/types/harness'

type TaskRunCardProps = {
  run: RunRecord
  onAdopt: (runId: string) => void
  onRetry: (runId: string) => void
  disableRetry?: boolean
}

export function TaskRunCard({ run, onAdopt, onRetry, disableRetry = false }: TaskRunCardProps) {
  const [detail, setDetail] = useState<'diff' | 'logs' | null>(null)
  const tone = runTone(run.status)
  const duration = formatDuration(run.durationMs)
  const statusLabel = run.status === 'passed' ? duration ?? '已通过' : runStatusLabel(run.status)
  const failureHint = run.status === 'failed' ? lastLogLine(run.rawOutput) : null
  const taskCopy = run.task !== (run.resultSummary || run.task) ? `任务：${run.task}` : null

  return (
    <article className={`run-card is-${tone}`}>
      <div className="run-card-head">
        <div className="run-card-title">
          <span className={`status-dot is-${tone}`} />
          <span>{run.status === 'pending' ? '已排队' : run.resultSummary || run.task}</span>
        </div>
        <span className="run-card-status">{statusLabel}</span>
      </div>

      <div className="run-card-body">
        {run.status === 'running' ? (
          <>
            <div className="run-progress-copy">{run.rawOutput || '正在分析仓库上下文...'}</div>
            <div className="run-progress-bar">
              <span className="run-progress-fill" />
            </div>
          </>
        ) : null}

        {run.status === 'pending' ? <div className="run-summary">任务：{run.task}</div> : null}
        {run.status === 'passed' && taskCopy ? <div className="run-summary">{taskCopy}</div> : null}
        {run.status === 'failed' ? (
          <>
            {taskCopy ? <div className="run-summary is-error">{taskCopy}</div> : null}
            <div className="run-hint">可能原因：{failureHint || '请查看日志详情。'}</div>
          </>
        ) : null}

        {codeFiles(run).length ? (
          <div className="file-chip-row">
            {codeFiles(run).map((file) => (
              <span key={file} className="file-chip">
                {file}
              </span>
            ))}
          </div>
        ) : null}

        {run.checkPassed ? <div className="run-check">✓ 校验已通过</div> : null}

        {detail === 'diff' && run.changedFiles.length ? (
          <div className="run-detail-block">
            {run.changedFiles.map((file) => (
              <div key={file}>{file}</div>
            ))}
          </div>
        ) : null}

        {detail === 'logs' && run.rawOutput ? <pre className="run-detail-block">{run.rawOutput}</pre> : null}
      </div>

      {run.status === 'passed' || run.status === 'failed' ? (
        <div className="run-actions run-actions-footer">
          {run.status === 'passed' ? (
            <>
              <button type="button" className="button-secondary" onClick={() => setDetail(detail === 'diff' ? null : 'diff')}>
                查看改动
              </button>
              <button type="button" className="button-secondary" onClick={() => setDetail(detail === 'logs' ? null : 'logs')}>
                日志
              </button>
              {!run.adoptedAt ? (
                <button type="button" className="button-primary" onClick={() => onAdopt(run.id)}>
                  采纳改动
                </button>
              ) : (
                <span className="run-adopted-flag">已采纳</span>
              )}
            </>
          ) : (
            <>
              <button type="button" className="button-secondary" onClick={() => setDetail(detail === 'logs' ? null : 'logs')}>
                查看日志
              </button>
              <button type="button" className="button-secondary" disabled={disableRetry} onClick={() => onRetry(run.id)}>
                重试
              </button>
            </>
          )}
        </div>
      ) : null}
    </article>
  )
}
