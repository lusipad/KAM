import type { RunRecord, RunStatus } from '@/types/harness'

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

export function lastLogLine(rawOutput: string) {
  return rawOutput
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .at(-1)
}

export function codeFiles(run: RunRecord) {
  return run.changedFiles.filter(Boolean).slice(0, 4)
}
