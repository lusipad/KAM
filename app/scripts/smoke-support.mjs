import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { spawn } from 'node:child_process'


export const repoRoot = path.resolve(import.meta.dirname, '..', '..')
export const backendDir = path.join(repoRoot, 'backend')
export const appDir = path.join(repoRoot, 'app')
export const outputDir = path.join(repoRoot, 'output')


export function resolvePython() {
  if (process.env.KAM_PYTHON) {
    return process.env.KAM_PYTHON
  }

  const candidates = [
    path.join(repoRoot, '.venv', 'Scripts', 'python.exe'),
    path.join(repoRoot, '.venv', 'bin', 'python'),
  ]
  for (const candidate of candidates) {
    if (fs.existsSync(candidate)) {
      return candidate
    }
  }

  return process.platform === 'win32' ? 'python' : 'python3'
}


export function waitForHealth(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs

  return new Promise((resolve, reject) => {
    const attempt = () => {
      http
        .get(`${url}/health`, (response) => {
          response.resume()
          if (response.statusCode === 200) {
            resolve()
            return
          }
          if (Date.now() > deadline) {
            reject(new Error(`Health check failed with ${response.statusCode}`))
            return
          }
          setTimeout(attempt, 400)
        })
        .on('error', () => {
          if (Date.now() > deadline) {
            reject(new Error('Timed out waiting for the backend health check'))
            return
          }
          setTimeout(attempt, 400)
        })
    }

    attempt()
  })
}


export function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      ...options,
    })
    child.on('close', (code) => {
      if (code === 0) {
        resolve()
        return
      }
      reject(new Error(`${command} exited with code ${code}`))
    })
  })
}


export function startBackend({
  port,
  databaseUrl,
  mockRuns = false,
  logPrefix,
  extraEnv = {},
}) {
  fs.mkdirSync(outputDir, { recursive: true })

  const python = resolvePython()
  const backendOut = fs.createWriteStream(path.join(outputDir, `${logPrefix}.out.log`))
  const backendErr = fs.createWriteStream(path.join(outputDir, `${logPrefix}.err.log`))

  const backend = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', String(port)], {
    cwd: backendDir,
    env: {
      ...process.env,
      DATABASE_URL: databaseUrl,
      ...(mockRuns ? { MOCK_RUNS: 'true' } : {}),
      ...extraEnv,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  backend.stdout.pipe(backendOut)
  backend.stderr.pipe(backendErr)

  let backendExited = false
  backend.on('close', () => {
    backendExited = true
  })

  return {
    backend,
    backendOut,
    backendErr,
    get backendExited() {
      return backendExited
    },
  }
}


export function stopBackend(handle) {
  if (!handle.backendExited) {
    handle.backend.kill()
  }
  handle.backendOut.end()
  handle.backendErr.end()
}
