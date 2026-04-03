import fs from 'node:fs'
import path from 'node:path'

import { backendDir, startBackend, stopBackend, waitForHealth } from './smoke-support.mjs'


const port = process.env.KAM_SMOKE_PORT || '8011'
const agent = process.env.KAM_SMOKE_AGENT || 'codex'
const timeoutMs = Number(process.env.KAM_REAL_SMOKE_TIMEOUT_MS || '180000')
const baseURL = `http://127.0.0.1:${port}`
const sentinel = 'KAM_REAL_AGENT_SMOKE_OK'


async function request(pathname, init = {}) {
  const response = await fetch(`${baseURL}${pathname}`, {
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
    ...init,
  })

  const text = await response.text()
  const payload = text ? JSON.parse(text) : null
  if (!response.ok) {
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : text || `${response.status} ${response.statusText}`.trim())
  }
  return payload
}


async function waitForRun(taskId, runId) {
  const deadline = Date.now() + timeoutMs

  while (Date.now() < deadline) {
    const detail = await request(`/api/tasks/${taskId}`)
    const run = detail.runs.find((item) => item.id === runId)
    if (!run) {
      throw new Error(`run ${runId} disappeared from task ${taskId}`)
    }
    if (run.status === 'passed' || run.status === 'failed' || run.status === 'cancelled') {
      return run
    }
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }

  throw new Error(`Timed out waiting for ${agent} run ${runId}`)
}


function smokePrompt() {
  return `Use the current scratch directory only. Print exactly ${sentinel} and exit.`
}


async function main() {
  const smokeDb = path.join(backendDir, 'storage', `smoke-agent-${agent}.db`)
  fs.rmSync(smokeDb, { force: true })

  const backend = startBackend({
    port,
    databaseUrl: `sqlite+aiosqlite:///./storage/${path.basename(smokeDb)}`,
    logPrefix: `smoke-agent-${agent}`,
  })

  try {
    await waitForHealth(baseURL, 20000)

    const task = await request('/api/tasks', {
      method: 'POST',
      body: JSON.stringify({
        title: `真实 agent smoke: ${agent}`,
        description: '验证非 mock agent 执行链路、初始 artifacts 和轮询收敛。',
        labels: ['smoke', 'real-agent'],
      }),
    })

    await request(`/api/tasks/${task.id}/refs`, {
      method: 'POST',
      body: JSON.stringify({
        kind: 'note',
        label: 'Smoke Contract',
        value: `The run must emit ${sentinel} in scratch mode.`,
      }),
    })
    await request(`/api/tasks/${task.id}/context/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        focus: '只验证真实 agent 执行链路，不触碰仓库工作区。',
      }),
    })

    const createdRun = await request(`/api/tasks/${task.id}/runs`, {
      method: 'POST',
      body: JSON.stringify({
        agent,
        task: smokePrompt(),
      }),
    })

    const finishedRun = await waitForRun(task.id, createdRun.id)
    if (finishedRun.status !== 'passed') {
      throw new Error(`${agent} run failed: ${finishedRun.resultSummary || finishedRun.rawOutput || 'unknown error'}`)
    }

    const artifacts = await request(`/api/runs/${createdRun.id}/artifacts`)
    const artifactTypes = new Set(artifacts.artifacts.map((artifact) => artifact.type))
    for (const required of ['task_snapshot', 'context_snapshot', 'task', 'stdout', 'summary']) {
      if (!artifactTypes.has(required)) {
        throw new Error(`missing required artifact: ${required}`)
      }
    }

    const outputText = artifacts.artifacts.map((artifact) => artifact.content).join('\n')
    if (!outputText.includes(sentinel)) {
      throw new Error(`${agent} smoke output did not include ${sentinel}`)
    }

    console.log(`Real agent smoke passed for ${agent}.`)
  } finally {
    stopBackend(backend)
  }
}


main().catch((error) => {
  console.error(error)
  process.exit(1)
})
