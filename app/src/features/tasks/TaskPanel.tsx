import { formatRelativeTime } from '@/lib/v3-ui'
import type { ContextSnapshotRecord, ReviewCompareRecord, RunArtifactRecord } from '@/types/v3'

type TaskPanelProps = {
  artifacts: RunArtifactRecord[]
  snapshots: ContextSnapshotRecord[]
  reviews: ReviewCompareRecord[]
  selectedRunLabel: string
}

export function TaskPanel({ artifacts, snapshots, reviews, selectedRunLabel }: TaskPanelProps) {
  return (
    <div className="task-panel">
      <section className="memory-section">
        <div className="memory-title">Artifacts</div>
        <div className="memory-subtle">{selectedRunLabel || '选择一个 run 查看产物'}</div>
        {artifacts.length ? (
          <div className="task-artifact-list">
            {artifacts.map((artifact) => (
              <article key={artifact.id} className="task-artifact-card">
                <div className="task-artifact-head">
                  <strong>{artifact.type}</strong>
                  <span>{formatRelativeTime(artifact.createdAt)}</span>
                </div>
                <pre className="task-artifact-content">{artifact.content}</pre>
              </article>
            ))}
          </div>
        ) : (
          <div className="memory-empty">当前没有 artifacts。</div>
        )}
      </section>

      <section className="memory-section">
        <div className="section-label">Snapshots</div>
        {snapshots.length ? (
          snapshots.map((snapshot) => (
            <article key={snapshot.id} className="memory-chip">
              <strong>{snapshot.summary}</strong>
              <span>{snapshot.focus || snapshot.content}</span>
            </article>
          ))
        ) : (
          <div className="memory-empty">还没有上下文快照。</div>
        )}
      </section>

      <section className="memory-section">
        <div className="section-label">Compare</div>
        {reviews.length ? (
          reviews.map((review) => (
            <article key={review.id} className="memory-chip">
              <strong>{review.title}</strong>
              <span>{review.summary || '暂无摘要'}</span>
            </article>
          ))
        ) : (
          <div className="memory-empty">还没有 compare 结果。</div>
        )}
      </section>
    </div>
  )
}
