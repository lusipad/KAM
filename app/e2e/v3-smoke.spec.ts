import { expect, test } from '@playwright/test'


test.beforeEach(async ({ page }) => {
  const response = await page.request.post('/api/dev/seed-demo', {
    data: { reset: true },
  })
  expect(response.ok()).toBeTruthy()
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(600)
})


test('home, thread, memory, watchers are reachable in v3', async ({ page }) => {
  await expect(page).toHaveTitle('KAM V3')
  await expect(page.getByText('需要你处理')).toBeVisible()
  await expect(page.getByText('后台进行中')).toBeVisible()
  await expect(page.getByText('最近更新')).toBeVisible()
  await expect(page.getByRole('button', { name: '监控', exact: true })).toBeVisible()

  await page.getByRole('button', { name: /修复登录超时/i }).click()
  await expect(page.locator('.message-row.is-user .message-bubble')).toContainText('登录 30 秒后超时，修一下。')
  await expect(page.locator('.run-card .run-summary')).toContainText(
    '已更新 token 刷新路径，移除重复超时分支，检查通过。',
  )

  await page.getByRole('banner').getByRole('button', { name: '记忆' }).click()
  await expect(page.getByText('AI 记忆')).toBeVisible()
  await expect(page.getByText('偏好', { exact: true })).toBeVisible()
  await expect(page.getByText('决策', { exact: true })).toBeVisible()
  await expect(page.getByText('经验', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: '监控', exact: true }).click()
  const watcherCard = page.locator('.watcher-card').filter({ hasText: 'CI 监控' }).first()
  await expect(page.getByText('监控 · 1 个运行中')).toBeVisible()
  await expect(watcherCard).toBeVisible()
  await expect(watcherCard.getByRole('button', { name: '立即执行' })).toBeVisible()
  await expect(watcherCard.getByRole('button', { name: '查看历史' })).toBeVisible()

  await watcherCard.getByRole('button', { name: '查看历史' }).click()
  await expect(page.getByText('main 分支 CI 失败')).toBeVisible()
  await expect(page.getByRole('button', { name: '打开线程' })).toBeVisible()

  await watcherCard.getByRole('button', { name: '编辑' }).click()
  await page.getByLabel('频率').fill('30m')
  await page.getByRole('button', { name: '保存修改' }).click()
  await expect(watcherCard.getByText('CI 流水线 · 每 30 分钟')).toBeVisible()
})
