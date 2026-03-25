import { expect, test } from '@playwright/test';

test.describe('KAM Lite', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('显示精简后的任务收件箱骨架', async ({ page }) => {
    await expect(page).toHaveTitle('KAM Lite');
    await expect(page.getByRole('complementary')).toBeVisible();
    await expect(page.getByRole('heading', { name: '任务收件箱' })).toBeVisible();
    await expect(page.getByRole('button', { name: '新建任务' })).toBeVisible();
  });

  test('可以打开外观设置面板', async ({ page }) => {
    await page.getByRole('button', { name: '外观设置' }).click();
    await expect(page.getByRole('heading', { name: '外观设置' })).toBeVisible();
    await expect(page.getByText('主题模式', { exact: true })).toBeVisible();
    await expect(page.getByText('强调色', { exact: true })).toBeVisible();
  });

  test('右侧区域按任务状态展示合适内容', async ({ page }) => {
    const focusedTask = page.getByText('Focused Task', { exact: true });
    const idleWorkspace = page.getByText('右侧只服务当前任务，不再平铺所有信息。', { exact: true });

    if ((await focusedTask.count()) > 0) {
      await expect(focusedTask).toBeVisible();
      await expect(page.getByRole('tab', { name: '概览' })).toBeVisible();
      await expect(page.getByRole('tab', { name: '资料' })).toBeVisible();
      await expect(page.getByRole('tab', { name: '执行' })).toBeVisible();
      await expect(page.getByRole('tab', { name: '收口' })).toBeVisible();
    } else {
      await expect(idleWorkspace).toBeVisible();
      await expect(page.getByText('先选任务，再进入工作台', { exact: true })).toBeVisible();
    }
  });
});
