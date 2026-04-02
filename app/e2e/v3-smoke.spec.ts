import { expect, test } from '@playwright/test'


test.beforeEach(async ({ page }) => {
  const response = await page.request.post('/api/dev/seed-harness', {
    data: { reset: true },
  })
  expect(response.ok()).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(600)
})


test('task-first harness workbench is reachable', async ({ page }) => {
  await expect(page).toHaveTitle('KAM V3')
  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()
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

test('mobile keeps task detail and artifact panel reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })

  await expect(page.locator('.feed-card-title').filter({ hasText: '切到 task-first harness' }).first()).toBeVisible()
  await expect(page.locator('.memory-title').filter({ hasText: 'Artifacts' })).toBeVisible()
  await expect(page.locator('.memory-subtle').filter({ hasText: 'claude-code · passed' })).toBeVisible()
})
