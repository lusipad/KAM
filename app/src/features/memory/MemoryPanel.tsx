import { runStatusLabel } from '@/lib/v3-ui'
import type { MemoryItem, ProjectSummary, RunRecord } from '@/types/v3'

type MemoryPanelProps = {
  project: ProjectSummary | null
  latestRun: RunRecord | null
  memories: MemoryItem[]
}

function groupMemories(memories: MemoryItem[]) {
  const groups = new Map<string, MemoryItem[]>()
  for (const memory of memories) {
    groups.set(memory.category, [...(groups.get(memory.category) ?? []), memory])
  }
  return groups
}

export function MemoryPanel({ project, latestRun, memories }: MemoryPanelProps) {
  const grouped = groupMemories(memories)
  const sections = [
    { label: 'PREFERENCES', items: grouped.get('preference') ?? [] },
    { label: 'DECISIONS', items: grouped.get('decision') ?? [] },
    { label: 'LEARNINGS', items: grouped.get('learning') ?? [] },
  ]

  return (
    <div className="memory-panel">
      <div className="memory-title">AI memory</div>
      <div className="memory-subtle">What KAM knows about this project</div>

      {sections.map(({ label, items }) => (
        <section key={label} className="memory-section">
          <div className="section-label">{label}</div>
          {items.length ? (
            items.map((item) => (
              <div key={item.id} className="memory-chip">
                <strong>{item.content}</strong>
                {item.rationale ? <span>{item.rationale}</span> : null}
              </div>
            ))
          ) : (
            <div className="memory-empty">Nothing captured yet.</div>
          )}
        </section>
      ))}

      <section className="memory-section">
        <div className="section-label">PROJECT CONTEXT</div>
        {project ? (
          <div className="memory-chip">
            <strong>Project</strong>
            <span>{project.title}</span>
          </div>
        ) : null}
        {project?.repoPath ? (
          <div className="memory-chip">
            <strong>Repo</strong>
            <span>{project.repoPath}</span>
          </div>
        ) : null}
        {latestRun ? (
          <div className="memory-chip">
            <strong>Last run</strong>
            <span>{runStatusLabel(latestRun.status)}{latestRun.resultSummary ? ` · ${latestRun.resultSummary}` : ''}</span>
          </div>
        ) : null}
      </section>
    </div>
  )
}
