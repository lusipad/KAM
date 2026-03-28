import type { FeedItem, RunRecord, RunStatus, ThreadSummary, WatcherRecord } from '@/types/v3'

export function formatRelativeTime(value: string | null) {
  if (!value) {
    return '刚刚'
  }

  const diffMs = new Date(value).getTime() - Date.now()
  const diffSeconds = Math.round(diffMs / 1000)
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['day', 60 * 60 * 24],
    ['hour', 60 * 60],
    ['minute', 60],
    ['second', 1],
  ]
  const formatter = new Intl.RelativeTimeFormat('zh-CN', { numeric: 'auto' })

  for (const [unit, size] of units) {
    if (Math.abs(diffSeconds) >= size || unit === 'second') {
      return formatter.format(Math.round(diffSeconds / size), unit)
    }
  }

  return '刚刚'
}

export function formatDuration(durationMs: number | null) {
  if (!durationMs || durationMs <= 0) {
    return null
  }
  if (durationMs >= 1000) {
    return `${(durationMs / 1000).toFixed(1)} 秒`
  }
  return `${durationMs} 毫秒`
}

export function runStatusLabel(status: RunStatus | null) {
  if (status === 'running') {
    return '执行中'
  }
  if (status === 'passed') {
    return '已通过'
  }
  if (status === 'failed') {
    return '失败'
  }
  if (status === 'pending') {
    return '排队中'
  }
  if (status === 'cancelled') {
    return '已取消'
  }
  return '历史'
}

export function inferProjectTitle(prompt: string) {
  const compact = prompt.replace(/\s+/g, ' ').trim()
  return compact.slice(0, 36) || '新项目'
}

export function inferThreadTitle(prompt: string) {
  const compact = prompt.replace(/\s+/g, ' ').trim()
  return compact.slice(0, 48) || '新对话'
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
    return '正在执行...'
  }
  if (thread.latestRunStatus === 'passed') {
    return '已通过，等待采纳'
  }
  if (thread.latestRunStatus === 'failed') {
    return '失败，需要处理'
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
    return 'CI 流水线'
  }
  if (sourceType === 'azure_devops') {
    return 'Azure DevOps'
  }
  if (sourceType === 'github' || sourceType === 'github_pr') {
    return 'GitHub'
  }
  return '监控'
}

export function watcherStatusLabel(status: WatcherRecord['status']) {
  if (status === 'active') {
    return '运行中'
  }
  if (status === 'draft') {
    return '待启用'
  }
  return '已暂停'
}

export function watcherEventStatusLabel(status: 'pending' | 'handled' | 'dismissed') {
  if (status === 'handled') {
    return '已处理'
  }
  if (status === 'dismissed') {
    return '已忽略'
  }
  return '待处理'
}

export function humanizeScheduleValue(value: string) {
  const normalized = value.trim()
  const match = normalized.match(/^(\d+)([mhd])$/i)
  if (!match) {
    return normalized
  }

  const amount = Number(match[1])
  const unit = match[2].toLowerCase()
  const label = unit === 'h' ? '小时' : unit === 'd' ? '天' : '分钟'
  return `每 ${amount} ${label}`
}

export function humanizeSchedule(watcher: WatcherRecord) {
  if (watcher.scheduleType === 'interval') {
    return humanizeScheduleValue(watcher.scheduleValue)
  }
  return `Cron 表达式 · ${watcher.scheduleValue}`
}

export function watcherDescription(watcher: WatcherRecord) {
  const repo = typeof watcher.config.repo === 'string' ? watcher.config.repo : null
  const board = typeof watcher.config.board === 'string' ? watcher.config.board : null
  const watch = typeof watcher.config.watch === 'string' ? watcher.config.watch : null
  const prefix = watcher.status === 'draft' ? '这是一份待确认的监控草稿。' : ''

  if (watcher.sourceType === 'ci_pipeline') {
    return `${prefix}持续检查 ${repo ?? '主分支'} 的构建失败，并把可直接处理的摘要推送到首页。`.trim()
  }
  if (watcher.sourceType === 'azure_devops') {
    return `${prefix}持续跟踪 ${board ?? '你的看板'} 上的新工作项，一旦需要处理就自动开线程。`.trim()
  }
  if (watcher.sourceType === 'github' || watcher.sourceType === 'github_pr') {
    if (watch === 'review_comments') {
      return `${prefix}持续盯住 ${repo ?? '你的仓库'} 的新评审评论，并把分流结果送回对应线程。`.trim()
    }
    return `${prefix}持续关注 ${repo ?? '你的仓库'} 的评审动态，并把事件路由到正确线程。`.trim()
  }
  return `${prefix}在后台持续监控来源，只把真正需要决策的事件推到你面前。`.trim()
}

export function watcherTargetSummary(watcher: WatcherRecord) {
  const repo = typeof watcher.config.repo === 'string' ? watcher.config.repo : null
  const board = typeof watcher.config.board === 'string' ? watcher.config.board : null
  const number = typeof watcher.config.number === 'number' ? `#${watcher.config.number}` : null

  if (watcher.sourceType === 'ci_pipeline') {
    return repo ?? '主分支'
  }
  if (watcher.sourceType === 'azure_devops') {
    return board ?? '分配给我的工作项'
  }
  if (watcher.sourceType === 'github' || watcher.sourceType === 'github_pr') {
    return [repo, number].filter(Boolean).join(' ') || '仓库活动'
  }
  return '后台来源'
}

export function watcherAutomationLabel(level: number) {
  if (level >= 3) {
    return '自动执行'
  }
  if (level === 2) {
    return '草稿并执行'
  }
  return '仅观察'
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
    return item.watcher?.name ?? '监控'
  }
  return item.task
}

export function codeFiles(run: RunRecord) {
  return run.changedFiles.filter(Boolean).slice(0, 4)
}
