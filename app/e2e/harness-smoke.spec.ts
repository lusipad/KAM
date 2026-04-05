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

test('mobile keeps task detail and artifact panel reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })

  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()
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
