import type { AutoDriveEventRecord, SuggestedTaskRefRecord, TaskDetail } from '@/types/harness'

export function metadataText(value: unknown) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

export function metadataBoolean(value: unknown) {
  return value === true
}

export function metadataList(value: unknown) {
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

export function metadataSuggestedRefs(value: unknown): SuggestedTaskRefRecord[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') {
      return []
    }
    const candidate = item as Record<string, unknown>
    const kind = metadataText(candidate.kind)
    const label = metadataText(candidate.label)
    const refValue = metadataText(candidate.value)
    if (!kind || !label || !refValue) {
      return []
    }
    return [
      {
        kind,
        label,
        value: refValue,
        metadata: candidate.metadata && typeof candidate.metadata === 'object' ? (candidate.metadata as Record<string, unknown>) : {},
      },
    ]
  })
}

export function metadataAutoDriveEvents(value: unknown): AutoDriveEventRecord[] {
  if (!Array.isArray(value)) {
    return []
  }
  return value.flatMap((item) => {
    if (!item || typeof item !== 'object') {
      return []
    }
    const candidate = item as Record<string, unknown>
    const recordedAt = metadataText(candidate.recordedAt)
    if (!recordedAt) {
      return []
    }
    return [
      {
        recordedAt,
        status: metadataText(candidate.status),
        action: metadataText(candidate.action),
        reason: metadataText(candidate.reason),
        summary: metadataText(candidate.summary),
        error: metadataText(candidate.error),
        taskId: metadataText(candidate.taskId),
        scopeTaskId: metadataText(candidate.scopeTaskId),
        runId: metadataText(candidate.runId),
        runTaskId: metadataText(candidate.runTaskId),
      },
    ]
  })
}

export function plannerAgentValue(value: unknown): 'codex' | 'claude-code' {
  return value === 'claude-code' ? 'claude-code' : 'codex'
}

export function plannerAgentLabel(value: string | null) {
  if (value === 'codex') {
    return 'Codex'
  }
  if (value === 'claude-code') {
    return 'Claude Code'
  }
  return null
}

export function planningReasonLabel(reason: string | null) {
  if (reason === 'failed_run_follow_up') {
    return '失败修复'
  }
  if (reason === 'passed_run_not_adopted') {
    return '采纳收口'
  }
  if (reason === 'review_compare_follow_up') {
    return 'compare 推进'
  }
  if (reason === 'task_next_step') {
    return '下一步'
  }
  return null
}

export function readPlanningMetadata(metadata: Record<string, unknown> | null | undefined) {
  const value = metadata ?? {}
  return {
    recommendedPrompt: metadataText(value.recommendedPrompt) ?? '',
    recommendedAgent: plannerAgentValue(value.recommendedAgent),
    acceptanceChecks: metadataList(value.acceptanceChecks),
    suggestedRefs: metadataSuggestedRefs(value.suggestedRefs),
  }
}

export function readTaskAutoDriveMetadata(metadata: Record<string, unknown> | null | undefined) {
  const value = metadata ?? {}
  return {
    enabled: metadataBoolean(value.autoDriveEnabled),
    status: metadataText(value.autoDriveStatus),
    lastAction: metadataText(value.autoDriveLastAction),
    lastReason: metadataText(value.autoDriveLastReason),
    lastSummary: metadataText(value.autoDriveLastSummary),
    recentEvents: metadataAutoDriveEvents(value.autoDriveRecentEvents),
  }
}

export function taskShouldPoll(detail: TaskDetail | null) {
  if (!detail) {
    return false
  }
  if (detail.runs.some((run) => run.status === 'pending' || run.status === 'running')) {
    return true
  }
  const autoDrive = readTaskAutoDriveMetadata(detail.metadata)
  return autoDrive.enabled && (autoDrive.status === 'running' || autoDrive.status === 'waiting_for_run')
}
