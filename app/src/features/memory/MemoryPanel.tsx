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
    { label: '偏好', items: grouped.get('preference') ?? [] },
    { label: '决策', items: grouped.get('decision') ?? [] },
    { label: '经验', items: grouped.get('learning') ?? [] },
  ]

  return (
    <div className="memory-panel">
      <div className="memory-title">AI 记忆</div>
      <div className="memory-subtle">KAM 已经记住的项目上下文</div>

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
            <div className="memory-empty">暂时还没有沉淀内容。</div>
          )}
        </section>
      ))}

      <section className="memory-section">
        <div className="section-label">项目上下文</div>
        {project ? (
          <div className="memory-chip">
            <strong>项目</strong>
            <span>{project.title}</span>
          </div>
        ) : null}
        {project?.repoPath ? (
          <div className="memory-chip">
            <strong>仓库</strong>
            <span>{project.repoPath}</span>
          </div>
        ) : null}
        {latestRun ? (
          <div className="memory-chip">
            <strong>最近一次执行</strong>
            <span>{runStatusLabel(latestRun.status)}{latestRun.resultSummary ? ` · ${latestRun.resultSummary}` : ''}</span>
          </div>
        ) : null}
      </section>
    </div>
  )
}
