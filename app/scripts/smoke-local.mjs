import path from 'node:path'
import fs from 'node:fs'

import { appDir, backendDir, run, startBackend, stopBackend, waitForHealth } from './smoke-support.mjs'


const port = process.env.KAM_SMOKE_PORT || '8010'
const baseURL = `http://127.0.0.1:${port}`


async function main() {
  const smokeDb = path.join(backendDir, 'storage', 'smoke-v3.db')
  fs.rmSync(smokeDb, { force: true })
  const backend = startBackend({
    port,
    databaseUrl: 'sqlite+aiosqlite:///./storage/smoke-v3.db',
    mockRuns: true,
    logPrefix: 'smoke-backend',
  })

  try {
    await waitForHealth(baseURL)

    if (process.platform === 'win32') {
      await run('cmd.exe', ['/c', 'npm', 'run', 'test:smoke'], {
        cwd: appDir,
        env: { ...process.env, PW_BASE_URL: baseURL },
      })
    } else {
      await run('npm', ['run', 'test:smoke'], {
        cwd: appDir,
        env: { ...process.env, PW_BASE_URL: baseURL },
      })
    }
  } finally {
    stopBackend(backend)
  }
}


main().catch((error) => {
  console.error(error)
  process.exit(1)
})
