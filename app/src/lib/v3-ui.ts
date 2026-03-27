import type { FeedItem, RunRecord, RunStatus, ThreadSummary, WatcherRecord } from '@/types/v3'

export function formatRelativeTime(value: string | null) {
  if (!value) {
    return 'Just now'
  }

  const diffMs = new Date(value).getTime() - Date.now()
  const diffSeconds = Math.round(diffMs / 1000)
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['day', 60 * 60 * 24],
    ['hour', 60 * 60],
    ['minute', 60],
    ['second', 1],
  ]
  const formatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

  for (const [unit, size] of units) {
    if (Math.abs(diffSeconds) >= size || unit === 'second') {
      return formatter.format(Math.round(diffSeconds / size), unit)
    }
  }

  return 'Just now'
}

export function formatDuration(durationMs: number | null) {
  if (!durationMs || durationMs <= 0) {
    return null
  }
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(1)}s`
  }
  return `${durationMs}ms`
}

export function runStatusLabel(status: RunStatus | null) {
  if (status === 'running') {
    return 'Running'
  }
  if (status === 'passed') {
    return 'Passed'
  }
  if (status === 'failed') {
    return 'Failed'
  }
  if (status === 'pending') {
    return 'Pending'
  }
  return 'History'
}

export function inferProjectTitle(prompt: string) {
  const compact = prompt.replace(/\s+/g, ' ').trim()
  return compact.slice(0, 36) || 'New project'
}

export function inferThreadTitle(prompt: string) {
  const compact = prompt.replace(/\s+/g, ' ').trim()
  return compact.slice(0, 48) || 'New conversation'
}

export function runTone(status: RunStatus | null) {
  if (status === 'running') {
    return 'amber'
  }
  if (status === 'passed') {
    return 'green'
  }
  if (status === 'failed') {
    return 'red'
  }
  return 'gray'
}

export function threadDotTone(thread: ThreadSummary) {
  if (thread.hasActiveRun) {
    return 'amber'
  }
  if (thread.latestRunStatus === 'passed') {
    return 'green'
  }
  if (thread.latestRunStatus === 'failed') {
    return 'red'
  }
  return 'gray'
}

export function threadMeta(thread: ThreadSummary) {
  if (thread.hasActiveRun) {
    return 'Running...'
  }
  if (thread.latestRunStatus === 'passed') {
    return 'Passed, waiting to adopt'
  }
  if (thread.latestRunStatus === 'failed') {
    return 'Failed, needs attention'
  }
  return formatRelativeTime(thread.updatedAt)
}

export function watcherGlyph(watcher: WatcherRecord) {
  if (watcher.sourceType === 'azure_devops') {
    return 'W'
  }
  if (watcher.sourceType === 'ci_pipeline') {
    return 'C'
  }
  return 'G'
}

export function watcherTone(sourceType: string | null | undefined) {
  if (sourceType === 'ci_pipeline') {
    return 'red'
  }
  if (sourceType === 'azure_devops' || sourceType === 'github_pr') {
    return 'purple'
  }
  return 'gray'
}

export function watcherSourceLabel(sourceType: string | null | undefined) {
  if (sourceType === 'ci_pipeline') {
    return 'CI pipeline'
  }
  if (sourceType === 'azure_devops') {
    return 'Azure DevOps'
  }
  if (sourceType === 'github' || sourceType === 'github_pr') {
    return 'GitHub'
  }
  return 'Watcher'
}

export function humanizeSchedule(watcher: WatcherRecord) {
  if (watcher.scheduleType === 'interval') {
    return `Every ${watcher.scheduleValue}`
  }
  return watcher.scheduleValue
}

export function watcherDescription(watcher: WatcherRecord) {
  const repo = typeof watcher.config.repo === 'string' ? watcher.config.repo : null
  const board = typeof watcher.config.board === 'string' ? watcher.config.board : null
  const watch = typeof watcher.config.watch === 'string' ? watcher.config.watch : null

  if (watcher.sourceType === 'ci_pipeline') {
    return `Watches ${repo ?? 'your main branch'} for build failures and pushes a ready-to-act summary into Home.`
  }
  if (watcher.sourceType === 'azure_devops') {
    return `Tracks ${board ?? 'your board'} for new work items, then opens a thread when something needs attention.`
  }
  if (watcher.sourceType === 'github' || watcher.sourceType === 'github_pr') {
    if (watch === 'review_comments') {
      return `Keeps watching ${repo ?? 'your repository'} for new review comments and routes the triage back into the right thread.`
    }
    return `Keeps an eye on ${repo ?? 'your repository'} for new review activity and routes it into the right thread.`
  }
  return 'Monitors a background source and surfaces only the events that need a decision.'
}

export function watcherTargetSummary(watcher: WatcherRecord) {
  const repo = typeof watcher.config.repo === 'string' ? watcher.config.repo : null
  const board = typeof watcher.config.board === 'string' ? watcher.config.board : null
  const number = typeof watcher.config.number === 'number' ? `#${watcher.config.number}` : null

  if (watcher.sourceType === 'ci_pipeline') {
    return repo ?? 'Main branch'
  }
  if (watcher.sourceType === 'azure_devops') {
    return board ?? 'Assigned work items'
  }
  if (watcher.sourceType === 'github' || watcher.sourceType === 'github_pr') {
    return [repo, number].filter(Boolean).join(' ') || 'Repository activity'
  }
  return 'Background source'
}

export function watcherAutomationLabel(level: number) {
  if (level >= 3) {
    return 'Auto-act'
  }
  if (level === 2) {
    return 'Draft + act'
  }
  return 'Observe only'
}

export function lastLogLine(rawOutput: string) {
  return rawOutput
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .at(-1)
}

export function feedLabel(item: FeedItem) {
  if (item.kind === 'watcher_event') {
    return item.watcher?.name ?? 'Watcher'
  }
  return item.task
}

export function codeFiles(run: RunRecord) {
  return run.changedFiles.filter(Boolean).slice(0, 4)
}
