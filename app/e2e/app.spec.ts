import { expect, test } from '@playwright/test';

test.describe('KAM Lite', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('显示 Lite 单工作台与核心说明', async ({ page }) => {
    await expect(page).toHaveTitle('KAM Lite');
    await expect(page.getByRole('complementary').getByText('KAM Lite')).toBeVisible();
    await expect(page.getByText('唯一工作带')).toBeVisible();
    await expect(page.getByText('任务定焦', { exact: true })).toBeVisible();
    await expect(page.getByText('结果收口', { exact: true })).toBeVisible();
  });

  test('可以打开外观设置面板', async ({ page }) => {
    await page.getByRole('button', { name: '外观设置' }).click();
    await expect(page.getByRole('heading', { name: '外观设置' })).toBeVisible();
    await expect(page.getByText('主题模式', { exact: true })).toBeVisible();
    await expect(page.getByText('强调色', { exact: true })).toBeVisible();
  });

  test('任务工作台主区可见', async ({ page }) => {
    await expect(page.getByRole('heading', { name: '任务池' })).toBeVisible();
    await expect(page.getByPlaceholder('任务标题')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Agent Runs' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Context Snapshot' })).toBeVisible();
  });
});
