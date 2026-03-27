import { useState } from 'react'

import { codeFiles, formatDuration, lastLogLine, runStatusLabel, runTone } from '@/lib/v3-ui'
import type { RunRecord } from '@/types/v3'

type RunCardProps = {
  run: RunRecord
  onAdopt: (runId: string) => void
  onRetry: (runId: string) => void
}

export function RunCard({ run, onAdopt, onRetry }: RunCardProps) {
  const [detail, setDetail] = useState<'diff' | 'logs' | null>(null)
  const tone = runTone(run.status)
  const duration = formatDuration(run.durationMs)
  const statusLabel = run.status === 'passed' ? duration ?? 'Passed' : runStatusLabel(run.status)
  const failureHint = run.status === 'failed' ? lastLogLine(run.rawOutput) : null

  return (
    <article className={`run-card is-${tone}`}>
      <div className="run-card-head">
        <div className="run-card-title">
          <span className={`status-dot is-${tone}`} />
          <span>{run.status === 'pending' ? 'Queued' : run.resultSummary || run.task}</span>
        </div>
        <span className="run-card-status">{statusLabel}</span>
      </div>

      <div className="run-card-body">
        {run.status === 'running' ? (
          <>
            <div className="run-progress-copy">{run.rawOutput || 'Working through the repository context...'}</div>
            <div className="run-progress-bar">
              <span className="run-progress-fill" />
            </div>
          </>
        ) : null}

        {run.status === 'pending' ? <div className="run-summary">Task: {run.task}</div> : null}
        {run.status === 'passed' ? <div className="run-summary">{run.resultSummary || run.task}</div> : null}
        {run.status === 'failed' ? (
          <>
            <div className="run-summary is-error">{run.resultSummary || 'The run failed.'}</div>
            <div className="run-hint">Likely cause: {failureHint || 'See logs for details.'}</div>
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

        {run.checkPassed ? <div className="run-check">✓ Checks passed</div> : null}

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
                View diff
              </button>
              <button type="button" className="button-secondary" onClick={() => setDetail(detail === 'logs' ? null : 'logs')}>
                Logs
              </button>
              {!run.adoptedAt ? (
                <button type="button" className="button-primary" onClick={() => onAdopt(run.id)}>
                  Adopt changes
                </button>
              ) : (
                <span className="run-adopted-flag">Adopted</span>
              )}
            </>
          ) : (
            <>
              <button type="button" className="button-secondary" onClick={() => setDetail(detail === 'logs' ? null : 'logs')}>
                View logs
              </button>
              <button type="button" className="button-secondary" onClick={() => onRetry(run.id)}>
                Retry
              </button>
            </>
          )}
        </div>
      ) : null}
    </article>
  )
}
