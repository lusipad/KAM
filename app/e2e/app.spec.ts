import { expect, test } from '@playwright/test';

test.describe('KAM Lite', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('显示新的 V2 工作区骨架', async ({ page }) => {
    await expect(page).toHaveTitle('KAM Lite');
    await expect(page.getByText('KAM', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('PROJECTS', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'New project' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Memory' })).toBeVisible();
    await expect(page.getByPlaceholder('描述你的目标...')).toBeVisible();
  });

  test('可以打开外观设置面板', async ({ page }) => {
    await page.getByRole('button', { name: '外观设置' }).click();
    await expect(page.getByRole('heading', { name: '外观设置' })).toBeVisible();
    await expect(page.getByText('主题模式', { exact: true })).toBeVisible();
    await expect(page.getByText('强调色', { exact: true })).toBeVisible();
  });

  test('可以切换到 Memory 视图并打开新项目弹窗', async ({ page }) => {
    await page.getByRole('button', { name: 'New project' }).click();
    await expect(page.getByRole('heading', { name: 'New project' })).toBeVisible();
    await page.keyboard.press('Escape');

    await page.getByRole('button', { name: 'Memory' }).click();
    await expect(page.getByRole('button', { name: '返回工作区' })).toBeVisible();
    await expect(page.getByText('PREFERENCES', { exact: true })).toBeVisible();
    await expect(page.getByText('DECISIONS', { exact: true })).toBeVisible();
    await expect(page.getByText('LEARNINGS', { exact: true })).toBeVisible();
  });
});
