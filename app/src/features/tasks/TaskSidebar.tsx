import { formatRelativeTime } from '@/lib/ui'
import type { TaskRecord } from '@/types/harness'

type TaskSidebarProps = {
  tasks: TaskRecord[]
  activeTaskId: string | null
  includeArchived: boolean
  onSelectTask: (taskId: string) => void
  onCreateTask: () => void
  onToggleArchived: () => void
}

function taskTone(task: TaskRecord) {
  if (task.dependencyState?.ready === false) {
    return 'red'
  }
  if (task.status === 'running' || task.status === 'in_progress') {
    return 'amber'
  }
  if (task.status === 'done' || task.status === 'verified') {
    return 'green'
  }
  if (task.status === 'blocked' || task.status === 'failed') {
    return 'red'
  }
  return 'gray'
}

function taskMeta(task: TaskRecord) {
  if (task.archivedAt) {
    return '已归档'
  }
  if (task.dependencyState?.ready === false && task.dependencyState.summary) {
    return task.dependencyState.summary
  }
  const label = task.labels.slice(0, 2).join(' · ')
  return label || formatRelativeTime(task.updatedAt)
}

export function TaskSidebar({ tasks, activeTaskId, includeArchived, onSelectTask, onCreateTask, onToggleArchived }: TaskSidebarProps) {
  return (
    <aside className="kam-sidebar">
      <div className="sidebar-brand">
        <div className="brand-mark">K</div>
        <div>
          <div className="brand-name">KAM</div>
          <div className="brand-subtle">Harness</div>
        </div>
      </div>

      <button type="button" className="active-rail" onClick={onCreateTask}>
        <span className="status-dot is-amber" />
        <span>{tasks.length ? `当前 ${tasks.length} 个任务` : '创建第一个任务'}</span>
      </button>

      <div className="sidebar-scroll">
        <section className="thread-group">
          <div className="group-label">Tasks</div>
          {tasks.map((task) => (
            <button
              type="button"
              key={task.id}
              className={`thread-row ${task.id === activeTaskId ? 'is-active' : ''}`}
              onClick={() => onSelectTask(task.id)}
            >
              <span className={`status-dot is-${taskTone(task)}`} />
              <span className="thread-copy">
                <span className="thread-title">{task.title}</span>
                <span className="thread-meta">{taskMeta(task)}</span>
              </span>
            </button>
          ))}
        </section>
      </div>

      <div className="sidebar-footer">
        <button type="button" className="footer-tab is-wide is-active" onClick={onCreateTask}>
          新建任务
        </button>
        <button type="button" className={`footer-tab is-wide ${includeArchived ? 'is-active' : ''}`} onClick={onToggleArchived}>
          {includeArchived ? '隐藏归档' : '显示归档'}
        </button>
      </div>
    </aside>
  )
}
