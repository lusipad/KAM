import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import { spawn } from 'node:child_process'


const repoRoot = path.resolve(import.meta.dirname, '..', '..')
const backendDir = path.join(repoRoot, 'backend')
const appDir = path.join(repoRoot, 'app')
const outputDir = path.join(repoRoot, 'output')
const port = process.env.KAM_SMOKE_PORT || '8010'
const baseURL = `http://127.0.0.1:${port}`


function resolvePython() {
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


function waitForHealth(url, timeoutMs = 15000) {
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


function run(command, args, options = {}) {
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


async function main() {
  fs.mkdirSync(outputDir, { recursive: true })

  const smokeDb = path.join(backendDir, 'storage', 'smoke-v3.db')
  fs.rmSync(smokeDb, { force: true })

  const python = resolvePython()
  const backendOut = fs.createWriteStream(path.join(outputDir, 'smoke-backend.out.log'))
  const backendErr = fs.createWriteStream(path.join(outputDir, 'smoke-backend.err.log'))

  const backend = spawn(python, ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', port], {
    cwd: backendDir,
    env: {
      ...process.env,
      DATABASE_URL: 'sqlite+aiosqlite:///./storage/smoke-v3.db',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  backend.stdout.pipe(backendOut)
  backend.stderr.pipe(backendErr)

  let backendExited = false
  backend.on('close', () => {
    backendExited = true
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
    if (!backendExited) {
      backend.kill()
    }
    backendOut.end()
    backendErr.end()
  }
}


main().catch((error) => {
  console.error(error)
  process.exit(1)
})
