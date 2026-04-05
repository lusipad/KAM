import fs from 'node:fs'
import { spawnSync } from 'node:child_process'
import path from 'node:path'

import { backendDir, outputDir, resolvePython, startBackend, stopBackend, waitForHealth } from './smoke-support.mjs'


const port = process.env.KAM_SMOKE_PORT || '8012'
const agent = process.env.KAM_SMOKE_AGENT || 'codex'
const timeoutMs = Number(process.env.KAM_REAL_SMOKE_TIMEOUT_MS || '180000')
const baseURL = `http://127.0.0.1:${port}`
const sentinel = 'KAM_REAL_AGENT_SMOKE_OK'
const repoSmokeMarker = 'repo-adopt-smoke'


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


function runChecked(command, args, options = {}) {
  const completed = spawnSync(command, args, {
    encoding: 'utf-8',
    ...options,
  })
  if (completed.status !== 0) {
    const detail = completed.stderr?.trim() || completed.stdout?.trim() || `${command} exited with code ${completed.status}`
    throw new Error(detail)
  }
  return completed.stdout.trim()
}


function createTempRepo() {
  fs.mkdirSync(outputDir, { recursive: true })
  const tempRoot = fs.mkdtempSync(path.join(outputDir, 'real-agent-smoke-'))
  const repoPath = path.join(tempRoot, 'repo')
  fs.mkdirSync(repoPath, { recursive: true })

  runChecked('git', ['init'], { cwd: repoPath })
  runChecked('git', ['config', 'user.name', 'KAM Smoke'], { cwd: repoPath })
  runChecked('git', ['config', 'user.email', 'kam-smoke@example.com'], { cwd: repoPath })

  const targetFile = path.join(repoPath, 'STATUS.md')
  fs.writeFileSync(targetFile, 'before\n', 'utf-8')
  fs.writeFileSync(path.join(repoPath, 'EXPECTED.txt'), `${sentinel}\n${repoSmokeMarker}\n`, 'utf-8')
  fs.writeFileSync(
    path.join(repoPath, 'check.py'),
    [
      'from pathlib import Path',
      '',
      "expected = Path('EXPECTED.txt').read_text(encoding='utf-8').strip()",
      "actual = Path('STATUS.md').read_text(encoding='utf-8').strip()",
      'if actual != expected:',
      "    raise SystemExit(f'unexpected STATUS.md: {actual!r}')",
      "print('ok')",
      '',
    ].join('\n'),
    'utf-8',
  )
  fs.writeFileSync(
    path.join(repoPath, 'AGENTS.md'),
    [
      'You are in a temporary smoke repository.',
      'Your only goal is to make `python check.py` pass by editing `STATUS.md`.',
      'Do not modify `EXPECTED.txt`, `check.py`, or this `AGENTS.md` file.',
      '',
    ].join('\n'),
    'utf-8',
  )
  runChecked('git', ['add', 'STATUS.md', 'EXPECTED.txt', 'check.py', 'AGENTS.md'], { cwd: repoPath })
  runChecked('git', ['commit', '-m', 'Seed temp repo for real agent smoke'], { cwd: repoPath })

  return { tempRoot, repoPath, targetFile }
}


function smokePrompt() {
  return [
    'Work only in the current repository.',
    'Make `python check.py` exit 0 by editing only `STATUS.md`.',
    'Do not modify `EXPECTED.txt`, `check.py`, or `AGENTS.md`.',
    'Run `python check.py` after your edit.',
  ].join('\n')
}


function assertAgentReady() {
  const python = resolvePython()
  const helperPath = path.join(backendDir, 'scripts', 'agent_readiness.py')
  runChecked(python, [helperPath, '--agent', agent])
}


async function main() {
  assertAgentReady()

  const smokeDb = path.join(backendDir, 'storage', `smoke-agent-${agent}.db`)
  fs.rmSync(smokeDb, { force: true })
  const repoFixture = createTempRepo()
  const keepRepo = process.env.KAM_REAL_SMOKE_KEEP_REPO === '1'

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
        description: '验证真实 agent 在临时 git 仓库中的改动、Lore commit 和 adopt 收口。',
        repoPath: repoFixture.repoPath,
        labels: ['smoke', 'real-agent'],
      }),
    })

    await request(`/api/tasks/${task.id}/refs`, {
      method: 'POST',
      body: JSON.stringify({
        kind: 'file',
        label: 'Smoke Target',
        value: 'STATUS.md',
      }),
    })
    await request(`/api/tasks/${task.id}/context/resolve`, {
      method: 'POST',
      body: JSON.stringify({
        focus: '验证真实 agent 改临时 git 仓库、自动提交并 adopt 回主仓库。',
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
    for (const required of ['task_snapshot', 'context_snapshot', 'task', 'stdout', 'summary', 'changed_files', 'patch']) {
      if (!artifactTypes.has(required)) {
        throw new Error(`missing required artifact: ${required}`)
      }
    }

    const changedFilesArtifact = artifacts.artifacts.find((artifact) => artifact.type === 'changed_files')
    if (changedFilesArtifact?.content !== '["STATUS.md"]') {
      throw new Error(`expected STATUS.md in changed_files artifact, got ${changedFilesArtifact?.content || '<missing>'}`)
    }

    const adopt = await request(`/api/runs/${createdRun.id}/adopt`, { method: 'POST' })
    if (!adopt.ok) {
      throw new Error(`adopt failed: ${adopt.error || 'unknown error'}`)
    }

    const adoptedContent = fs.readFileSync(repoFixture.targetFile, 'utf-8').replace(/\r\n/g, '\n').trim()
    if (adoptedContent !== `${sentinel}\n${repoSmokeMarker}`) {
      throw new Error(`unexpected adopted file content: ${JSON.stringify(adoptedContent)}`)
    }
    runChecked('python', ['check.py'], { cwd: repoFixture.repoPath })

    const commitMessage = runChecked('git', ['log', '-1', '--pretty=%B'], { cwd: repoFixture.repoPath })
    for (const required of ['Constraint:', 'Directive:', 'Related: task/', 'Related: run/']) {
      if (!commitMessage.includes(required)) {
        throw new Error(`expected ${required} in adopted commit message`)
      }
    }

    console.log(`Real agent repo smoke passed for ${agent}.`)
  } finally {
    stopBackend(backend)
    if (!keepRepo) {
      fs.rmSync(repoFixture.tempRoot, { recursive: true, force: true })
    }
  }
}


main().catch((error) => {
  console.error(error)
  process.exit(1)
})
