import fs from 'node:fs'
import path from 'node:path'

import { backendDir, repoRoot, startBackend, stopBackend, waitForHealth } from './smoke-support.mjs'


const port = process.env.KAM_SOAK_PORT || '8011'
const baseURL = `http://127.0.0.1:${port}`
const durationMs = readPositiveInt('KAM_SOAK_DURATION_MS', 15 * 60 * 1000)
const pollMs = readPositiveInt('KAM_SOAK_POLL_MS', 2000)
const taskIntervalMs = readPositiveInt('KAM_SOAK_TASK_INTERVAL_MS', 10000)
const settleMs = readPositiveInt('KAM_SOAK_SETTLE_MS', 5000)
const inactivityMs = Math.max(readPositiveInt('KAM_SOAK_INACTIVITY_MS', 20000), taskIntervalMs * 3, pollMs * 5)
const maxRecentEvents = 12
const logPrefix = process.env.KAM_SOAK_LOG_PREFIX || 'soak-backend'
const resultFile = process.env.KAM_SOAK_RESULT_FILE || null
const storageKey = process.env.KAM_SOAK_STORAGE_KEY || logPrefix
const relativeStoragePath = toPosixPath(path.join('.', 'storage', 'soak', storageKey))
const relativeDatabasePath = toPosixPath(path.join(relativeStoragePath, 'kam-harness.db'))
const relativeRunRoot = toPosixPath(path.join(relativeStoragePath, 'runs'))
const soakStorageDir = path.join(backendDir, 'storage', 'soak', storageKey)


function readPositiveInt(name, fallback) {
  const raw = process.env[name]
  if (!raw) {
    return fallback
  }

  const value = Number.parseInt(raw, 10)
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`Expected ${name} to be a positive integer, received: ${raw}`)
  }
  return value
}


function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}


function toPosixPath(value) {
  return value.split(path.sep).join('/')
}


function emitResult(payload) {
  const text = JSON.stringify(payload, null, 2)
  console.log(text)
  if (resultFile) {
    fs.writeFileSync(resultFile, `${text}\n`, 'utf8')
  }
}


async function request(pathname, { method = 'GET', body } = {}) {
  const response = await fetch(`${baseURL}${pathname}`, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })

  if (!response.ok) {
    throw new Error(`${method} ${pathname} failed with ${response.status}: ${await response.text()}`)
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}


async function createSoakRootTask(index) {
  const task = await request('/api/tasks', {
    method: 'POST',
    body: {
      title: `Autodrive soak root ${index}`,
      description: '持续给全局无人值守注入新的 root task，验证长时轮询期间不会卡死或失控膨胀。',
      repoPath: repoRoot,
      status: 'in_progress',
      priority: index % 2 === 0 ? 'high' : 'medium',
      labels: ['dogfood', 'soak', 'autodrive'],
    },
  })

  await request(`/api/tasks/${task.id}/refs`, {
    method: 'POST',
    body: {
      kind: 'file',
      label: 'Repo Root',
      value: path.join(repoRoot, 'README.md'),
    },
  })

  return task
}


function assertHealthyStatus(status, progressState) {
  if (!status.enabled) {
    throw new Error('Global autodrive unexpectedly became disabled during soak')
  }
  if (status.status === 'disabled') {
    throw new Error('Global autodrive reported a disabled status during soak')
  }
  if (status.status === 'error') {
    throw new Error(`Global autodrive entered error state: ${status.error || status.summary}`)
  }
  if (!Array.isArray(status.recentEvents)) {
    throw new Error('Global autodrive status is missing recentEvents')
  }
  if (status.recentEvents.length > maxRecentEvents) {
    throw new Error(`Global autodrive recentEvents exceeded ${maxRecentEvents}: ${status.recentEvents.length}`)
  }

  const latestEventKey = status.recentEvents.at(-1)
    ? `${status.recentEvents.at(-1).recordedAt}:${status.recentEvents.at(-1).reason ?? status.recentEvents.at(-1).status ?? 'event'}`
    : null
  const currentProgressKey = `${status.loopCount}:${status.updatedAt ?? ''}:${status.currentTaskId ?? ''}:${latestEventKey ?? ''}`
  if (currentProgressKey !== progressState.lastKey) {
    progressState.lastKey = currentProgressKey
    progressState.lastProgressAt = Date.now()
  }

  if (Date.now() - progressState.lastProgressAt > inactivityMs) {
    throw new Error(`Global autodrive made no progress for ${inactivityMs}ms`)
  }
}


async function verifyCreatedRoots(createdRoots) {
  const tasksPayload = await request('/api/tasks')
  const tasks = tasksPayload.tasks
  const childrenByParent = new Map()

  for (const task of tasks) {
    const parentTaskId = task.metadata?.parentTaskId
    if (!parentTaskId) {
      continue
    }
    if (!childrenByParent.has(parentTaskId)) {
      childrenByParent.set(parentTaskId, [])
    }
    childrenByParent.get(parentTaskId).push(task)
  }

  const eligibleRoots = createdRoots.filter((item) => item.createdAt <= Date.now() - Math.max(taskIntervalMs, settleMs))
  if (!eligibleRoots.length) {
    throw new Error('No eligible soak roots were created early enough to verify processing')
  }

  for (const root of eligibleRoots) {
    const children = childrenByParent.get(root.id) || []
    if (!children.length) {
      throw new Error(`Soak root ${root.id} never produced a follow-up task`)
    }

    const detail = await request(`/api/tasks/${children[0].id}`)
    const latestRun = detail.runs.at(-1)
    if (!latestRun || latestRun.status !== 'passed') {
      throw new Error(`Follow-up task ${children[0].id} for soak root ${root.id} did not complete with a passed run`)
    }
  }

  return {
    totalTasks: tasks.length,
    verifiedRoots: eligibleRoots.length,
  }
}


async function main() {
  fs.rmSync(soakStorageDir, { force: true, recursive: true })

  const backend = startBackend({
    port,
    databaseUrl: `sqlite+aiosqlite:///${relativeDatabasePath}`,
    mockRuns: true,
    logPrefix,
    extraEnv: {
      STORAGE_PATH: relativeStoragePath,
      RUN_ROOT: relativeRunRoot,
    },
  })

  const createdRoots = []
  let stopAttempted = false

  try {
    await waitForHealth(baseURL)
    await request('/api/dev/seed-harness', { method: 'POST', body: { reset: true } })

    for (let index = 1; index <= 2; index += 1) {
      const task = await createSoakRootTask(index)
      createdRoots.push({ id: task.id, createdAt: Date.now() })
    }

    const startResult = await request('/api/tasks/autodrive/global/start', { method: 'POST' })
    if (!startResult.enabled) {
      throw new Error('Failed to enable global autodrive for soak validation')
    }

    const progressState = {
      lastKey: '',
      lastProgressAt: Date.now(),
    }

    const startedAt = Date.now()
    let nextTaskAt = startedAt + taskIntervalMs
    let createdCount = createdRoots.length

    while (Date.now() - startedAt < durationMs) {
      if (Date.now() >= nextTaskAt) {
        createdCount += 1
        const task = await createSoakRootTask(createdCount)
        createdRoots.push({ id: task.id, createdAt: Date.now() })
        nextTaskAt += taskIntervalMs
      }

      const status = await request('/api/tasks/autodrive/global')
      assertHealthyStatus(status, progressState)
      await sleep(pollMs)
    }

    await sleep(settleMs)

    const finalStatus = await request('/api/tasks/autodrive/global')
    assertHealthyStatus(finalStatus, progressState)
    const verification = await verifyCreatedRoots(createdRoots)

    await request('/api/tasks/autodrive/global/stop', { method: 'POST' })
    stopAttempted = true

    emitResult({
      status: 'ok',
      baseURL,
      durationMs,
      pollMs,
      taskIntervalMs,
      settleMs,
      createdRootTasks: createdRoots.length,
      finalLoopCount: finalStatus.loopCount,
      finalRecentEvents: finalStatus.recentEvents.length,
      finalStatus: finalStatus.status,
      verification,
      logPrefix,
    })
  } finally {
    if (!stopAttempted) {
      try {
        await request('/api/tasks/autodrive/global/stop', { method: 'POST' })
      } catch {
        // Ignore cleanup failures after the main validation has already failed.
      }
    }
    stopBackend(backend)
  }
}


main().catch((error) => {
  if (resultFile) {
    fs.writeFileSync(
      resultFile,
      `${JSON.stringify(
        {
          status: 'failed',
          error: error instanceof Error ? error.message : String(error),
          logPrefix,
        },
        null,
        2,
      )}\n`,
      'utf8',
    )
  }
  console.error(error)
  process.exit(1)
})
