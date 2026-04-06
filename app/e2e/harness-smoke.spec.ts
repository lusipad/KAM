import { expect, test } from '@playwright/test'

test.describe.configure({ mode: 'serial' })


test.beforeEach(async ({ page }) => {
  const response = await page.request.post('/api/dev/seed-harness', {
    data: { reset: true },
  })
  expect(response.ok()).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(600)
})


test('task-first harness workbench is reachable', async ({ page }) => {
  await expect(page).toHaveTitle('KAM Harness')
  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()
  await expect(page.locator('.feed-card-title').filter({ hasText: '让 KAM 自己排工作' }).first()).toBeVisible()
  await expect(page.getByRole('main').getByText('Refs', { exact: true })).toBeVisible()
  await expect(page.getByRole('main').getByText('Context Snapshot', { exact: true })).toBeVisible()
  await expect(page.getByRole('main').getByText('Runs', { exact: true })).toBeVisible()
  await expect(page.getByRole('main').getByText('Compare', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '继续推进当前任务' })).toBeVisible()
  await expect(page.getByRole('main').getByText('[file] PRD')).toBeVisible()

  await expect(page.locator('.run-card').first()).toContainText('Task')
  await expect(page.locator('.run-card').filter({ hasText: '默认入口已切到 task-first workbench' }).first()).toBeVisible()

  await page.getByRole('button', { name: '对比最近两个 Run' }).click()
  await expect(page.locator('.task-list-row').filter({ hasText: '对比 2 个 run' }).first()).toBeVisible()

  await expect(page.locator('.memory-title').filter({ hasText: 'Artifacts' })).toBeVisible()
  await expect(page.locator('.task-artifact-card').filter({ hasText: 'stdout' }).first()).toBeVisible()
  await expect(page.locator('.task-artifact-content').filter({ hasText: '前端主入口已切换。' }).first()).toBeVisible()
})

test('can let KAM plan follow-up tasks from the current task', async ({ page }) => {
  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()

  await page.getByRole('button', { name: '让 KAM 自己排工作' }).click()

  await expect(page.getByRole('main').getByText('采纳并验证：', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('main').getByText('根据 compare 推进：', { exact: false }).first()).toBeVisible()
  await expect(page.locator('.thread-title').filter({ hasText: '采纳并验证：' }).first()).toBeVisible()
  await expect(page.locator('.thread-title').filter({ hasText: '根据 compare 推进：' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '直接开跑' }).first()).toBeVisible()

  await page.getByRole('button', { name: '直接开跑' }).first().click()
  await expect(page.locator('.feed-card-title').filter({ hasText: '采纳并验证：' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '来源 · 采纳收口' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '用推荐 Prompt 开跑' })).toBeVisible()
  await expect(page.locator('.task-list-row').filter({ hasText: '[file] 候选文件' }).first()).toBeVisible()
  await expect(page.locator('.run-card').filter({ hasText: '已完成 mock run：收口父任务' }).first()).toBeVisible()
})

test('can let KAM dispatch the next runnable task from the queue', async ({ page }) => {
  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()

  await page.getByRole('button', { name: '让 KAM 接下一张' }).click()

  await expect(page.locator('.feed-card-title').filter({ hasText: '采纳并验证：' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '状态 · in_progress' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '来源 · 采纳收口' }).first()).toBeVisible()
  await expect(page.locator('.run-card').filter({ hasText: '已完成 mock run：收口父任务' }).first()).toBeVisible()
})

test('can let KAM continue the current task family', async ({ page }) => {
  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()

  await page.getByRole('button', { name: '继续推进当前任务' }).click()

  await expect(page.locator('.feed-card-title').filter({ hasText: '采纳并验证：' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '来源 · 采纳收口' }).first()).toBeVisible()
  await expect(page.locator('.run-card').filter({ hasText: '已完成 mock run：收口父任务' }).first()).toBeVisible()
})

test('can let KAM continue the current task with an automatic decision', async ({ page }) => {
  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()

  await page.getByRole('button', { name: '继续推进当前任务' }).click()

  await expect(page.locator('.feed-card-title').filter({ hasText: '采纳并验证：' }).first()).toBeVisible()
  await expect(page.locator('.feed-card-title').filter({ hasText: '自动推进结果' }).first()).toBeVisible()
  await expect(page.locator('.feed-card-subtle').filter({ hasText: '已先拆后跑：' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '原因 · 已挑出下一张可跑任务' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '来源 · planned_task' }).first()).toBeVisible()
})

test('can enter self-driving mode for the current task family', async ({ page }) => {
  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()

  await page.getByRole('button', { name: '进入无人值守' }).click()

  await expect(page.getByRole('button', { name: '停止无人值守' })).toBeVisible()
  await expect(page.locator('.task-list-row').filter({ hasText: '无人值守' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '状态 · 已开启' }).first()).toBeVisible()
  await expect.poll(async () => {
    const response = await page.request.get('/api/tasks')
    const payload = await response.json()
    return payload.tasks.length
  }).toBe(3)
  await expect.poll(async () => {
    const response = await page.request.get('/api/tasks/task-harness-cutover')
    const payload = await response.json()
    return ['dispatched_next_runnable_task', 'no_high_value_action'].includes(payload.metadata.autoDriveLastReason)
  }).toBeTruthy()
})

test('can enter global self-driving mode across task families', async ({ page }) => {
  const secondRootResponse = await page.request.post('/api/tasks', {
    data: {
      title: '推进第二个 task family',
      description: '验证 KAM 会跨 family 接活',
      repoPath: 'D:/Repos/KAM',
      status: 'in_progress',
      priority: 'medium',
      labels: ['dogfood', 'global'],
    },
  })
  expect(secondRootResponse.ok()).toBeTruthy()
  const secondRoot = await secondRootResponse.json()

  await expect(page.getByRole('button', { name: '开启全局无人值守' })).toBeVisible()
  await page.getByRole('button', { name: '开启全局无人值守' }).click()

  await expect(page.getByRole('button', { name: '停止全局无人值守' })).toBeVisible()
  await expect(page.locator('.feed-card-title').filter({ hasText: '全局无人值守' }).first()).toBeVisible()
  await expect.poll(async () => {
    const response = await page.request.get('/api/tasks/autodrive/global')
    const payload = await response.json()
    return payload.lastReason
  }).toBe('no_high_value_action')
  await expect.poll(async () => {
    const response = await page.request.get('/api/tasks')
    const payload = await response.json()
    return payload.tasks.filter((item: { metadata: { parentTaskId?: string } }) => item.metadata.parentTaskId === secondRoot.id).length
  }).toBeGreaterThan(0)
})

test('can block a task with dependencies from the workbench', async ({ page }) => {
  const prerequisiteResponse = await page.request.post('/api/tasks', {
    data: {
      title: '先完成前置任务',
      description: '这是后续任务的前置依赖',
      repoPath: 'D:/Repos/KAM',
      status: 'open',
      priority: 'high',
      labels: ['dogfood', 'dependency'],
    },
  })
  expect(prerequisiteResponse.ok()).toBeTruthy()
  const prerequisite = await prerequisiteResponse.json()

  const blockedTaskResponse = await page.request.post('/api/tasks', {
    data: {
      title: '等待依赖完成的任务',
      description: '依赖没完成时不应自动继续',
      repoPath: 'D:/Repos/KAM',
      status: 'open',
      priority: 'medium',
      labels: ['dogfood', 'dependency'],
    },
  })
  expect(blockedTaskResponse.ok()).toBeTruthy()

  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(600)
  await page.locator('.thread-title').filter({ hasText: '等待依赖完成的任务' }).first().click()

  await page.getByPlaceholder('依赖任务 ID').fill(prerequisite.id)
  await page.getByRole('button', { name: '添加依赖' }).click()

  await expect(page.locator('.file-chip').filter({ hasText: '依赖 · 阻塞中' }).first()).toBeVisible()
  await expect(page.locator('.task-hero-card .task-list-row').filter({ hasText: '依赖状态' }).first()).toContainText('依赖未完成：先完成前置任务')
  await expect(page.getByRole('button', { name: '继续推进当前任务' })).toBeDisabled()
  await expect(page.getByRole('button', { name: '让 KAM 自己排工作' })).toBeDisabled()
  await expect(page.locator('.composer-submit')).toBeDisabled()
})

test('mobile keeps task detail and artifact panel reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })

  const taskTitle = page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()
  await taskTitle.scrollIntoViewIfNeeded()
  await expect(taskTitle).toBeVisible()
  await expect(page.locator('.memory-title').filter({ hasText: 'Artifacts' })).toBeVisible()
  await expect(page.locator('.memory-subtle').filter({ hasText: 'codex · passed' })).toBeVisible()
})

test('can create a task, add refs, generate a snapshot, launch runs, and compare them', async ({ page }) => {
  await page.getByRole('button', { name: '新建任务' }).first().click()

  await page.getByPlaceholder('例如：把当前默认前端主入口切成 task-first workbench').fill('把 run runtime 切成 task-native')
  await page.getByRole('button', { name: '创建任务' }).click()

  await expect(page.locator('.feed-card-title').filter({ hasText: '把 run runtime 切成 task-native' }).first()).toBeVisible()
  await page.getByPlaceholder('任务标题').fill('把 task-native run 收口到日常开发台')
  await page.getByPlaceholder('状态').fill('in_progress')
  await page.getByPlaceholder('优先级').fill('high')
  await page.getByPlaceholder('标签，逗号分隔').fill('dogfood, editing')
  await page.getByRole('button', { name: '保存任务设置' }).click()
  await expect(page.locator('.feed-card-title').filter({ hasText: '把 task-native run 收口到日常开发台' }).first()).toBeVisible()

  await page.getByPlaceholder('kind').fill('file')
  await page.getByPlaceholder('label').fill('Run Engine')
  await page.getByPlaceholder('value').fill('backend/services/run_engine.py')
  await page.getByRole('button', { name: '添加引用' }).click()

  await expect(page.locator('.task-list-row').filter({ hasText: '[file] Run Engine' }).first()).toBeVisible()

  await page.getByPlaceholder('可选 focus，例如：先切前端主入口').fill('先把 task run 挂到 task 下')
  await page.getByRole('button', { name: '生成快照' }).click()

  await expect(page.locator('.task-list-row').filter({ hasText: '把 task-native run 收口到日常开发台 · 1 refs' }).first()).toBeVisible()
  await expect(page.locator('.memory-chip').filter({ hasText: '先把 task run 挂到 task 下' }).first()).toBeVisible()

  await page.getByPlaceholder('输入这轮要执行的任务...').fill('先落 task-native run API')
  await page.locator('.composer-submit').click()
  await expect(page.locator('.run-card').filter({ hasText: '已完成 mock run：先落 task-native run API' }).first()).toBeVisible()

  await page.getByRole('button', { name: 'Claude Code' }).click()
  await page.getByPlaceholder('输入这轮要执行的任务...').fill('再补 compare 和 artifact 面板')
  await page.locator('.composer-submit').click()
  await expect(page.locator('.run-card').filter({ hasText: '已完成 mock run：再补 compare 和 artifact 面板' }).first()).toBeVisible()

  await page.getByRole('button', { name: '对比最近两个 Run' }).click()
  await expect(page.locator('.task-list-row').filter({ hasText: '对比 2 个 run' }).first()).toBeVisible()
  await expect(page.locator('.task-artifact-card').filter({ hasText: 'task_snapshot' }).first()).toBeVisible()

  await page.getByRole('button', { name: '归档任务' }).click()
  await expect(page.locator('.feed-card-title').filter({ hasText: '把 task-native run 收口到日常开发台' }).first()).toBeVisible()
  await expect(page.locator('.file-chip').filter({ hasText: '状态 · archived' })).toBeVisible()
  await expect(page.getByRole('button', { name: '隐藏归档' })).toBeVisible()
})
