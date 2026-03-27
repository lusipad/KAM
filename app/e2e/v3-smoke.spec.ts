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
  await expect(page.getByText('NEEDS YOUR ATTENTION')).toBeVisible()
  await expect(page.getByText('RUNNING IN BACKGROUND')).toBeVisible()
  await expect(page.getByText('RECENT')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Watchers' })).toBeVisible()

  await page.getByRole('button', { name: /Fix login timeout/i }).click()
  await expect(page.locator('.message-row.is-user .message-bubble')).toContainText('Login timeout after 30s. Fix this.')
  await expect(page.locator('.run-card .run-summary')).toContainText(
    'Updated the token refresh path, removed the duplicate timeout branch, and checks passed.',
  )

  await page.getByRole('banner').getByRole('button', { name: 'Memory' }).click()
  await expect(page.getByText('AI memory')).toBeVisible()
  await expect(page.getByText('PREFERENCES')).toBeVisible()
  await expect(page.getByText('DECISIONS')).toBeVisible()
  await expect(page.getByText('LEARNINGS')).toBeVisible()

  await page.getByRole('button', { name: 'Watchers' }).click()
  await expect(page.getByText('Watchers · 1 active')).toBeVisible()
  await expect(page.getByText('CI monitor')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Run now' })).toBeVisible()
})
