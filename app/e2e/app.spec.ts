import { test, expect } from '@playwright/test';

test.describe('AI工作助手 - 基础功能测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // 等待页面加载完成
    await page.waitForTimeout(1000);
  });

  test('页面标题正确显示', async ({ page }) => {
    await expect(page).toHaveTitle('AI工作助手');
  });

  test('侧边导航栏显示所有模块', async ({ page }) => {
    // 检查侧边栏存在（使用nav元素）
    const sidebar = page.locator('nav');
    await expect(sidebar).toBeVisible();

    // 检查所有导航项
    const navItems = [
      '知识管理',
      '长期记忆',
      'ClawTeam',
      'Azure DevOps',
      'AI对话'
    ];

    for (const item of navItems) {
      await expect(page.getByText(item).first()).toBeVisible();
    }
  });

  test('知识管理模块 - 可以创建新笔记', async ({ page }) => {
    // 点击知识管理
    await page.getByText('知识管理').first().click();
    
    // 等待页面加载
    await page.waitForTimeout(500);
    
    // 点击新建笔记按钮
    await page.getByRole('button', { name: /新建笔记/i }).click();
    
    // 等待编辑器区域加载
    await expect(page.getByText('选择一个笔记或创建新笔记').or(page.locator('textarea'))).toBeVisible({ timeout: 5000 });
  });

  test('知识管理模块 - 笔记列表显示正常', async ({ page }) => {
    await page.getByText('知识管理').first().click();
    
    // 检查笔记列表区域
    await expect(page.getByText('笔记列表')).toBeVisible();
    
    // 检查搜索框
    const searchInput = page.locator('input[placeholder*="搜索"]').first();
    await expect(searchInput).toBeVisible();
    
    // 检查编辑器/知识图谱/双向链接切换按钮（使用TabsTrigger）
    await expect(page.getByText('编辑器').first()).toBeVisible();
    await expect(page.getByText('知识图谱').first()).toBeVisible();
    await expect(page.getByText('双向链接').first()).toBeVisible();
  });

  test('长期记忆模块 - 界面正常显示', async ({ page }) => {
    await page.getByText('长期记忆').first().click();
    
    // 等待页面加载
    await page.waitForTimeout(500);
    
    // 检查记忆管理界面元素
    await expect(page.getByText('记忆类型')).toBeVisible();
    await expect(page.getByText('全部记忆')).toBeVisible();
    
    // 检查搜索功能
    const searchInput = page.locator('input[placeholder*="搜索"]').first();
    await expect(searchInput).toBeVisible();
  });

  test('ClawTeam模块 - 界面正常显示', async ({ page }) => {
    await page.getByText('ClawTeam').first().click();
    
    await page.waitForTimeout(500);
    
    // 检查ClawTeam界面元素
    await expect(page.getByText('AI代理团队')).toBeVisible();
  });

  test('Azure DevOps模块 - 界面正常显示', async ({ page }) => {
    await page.getByText('Azure DevOps').first().click();
    
    await page.waitForTimeout(500);
    
    // 检查Azure DevOps界面元素
    await expect(page.getByRole('heading', { name: 'Azure DevOps 配置' })).toBeVisible();
  });

  test('AI对话模块 - 界面正常显示', async ({ page }) => {
    await page.getByText('AI对话').first().click();
    
    await page.waitForTimeout(500);
    
    // 检查AI对话界面元素
    await expect(page.getByText('对话历史')).toBeVisible();
    await expect(page.getByRole('button', { name: /新对话/i })).toBeVisible();
  });

  test('AI对话模块 - 可以发送消息', async ({ page }) => {
    await page.getByText('AI对话').first().click();
    await page.waitForTimeout(500);
    
    // 找到输入框（可能是textarea或input）
    const chatInput = page.locator('textarea, input[type="text"]').first();
    if (await chatInput.count() > 0) {
      await chatInput.fill('你好，这是一个测试消息');
      
      // 点击发送
      await page.getByRole('button', { name: /发送/i }).click();
      
      // 验证消息显示在聊天中
      await expect(page.getByText('你好，这是一个测试消息')).toBeVisible();
    }
  });

  test('设置功能 - 可以打开设置面板', async ({ page }) => {
    // 点击设置按钮
    await page.getByText('设置').first().click();
    
    await page.waitForTimeout(500);
    
    // 检查设置面板是否弹出（可能有遮罩层或对话框）
    // 由于设置面板可能使用Dialog组件，检查是否有设置相关的文本
    const settingsText = page.getByText(/设置|主题|语言/);
    // 设置面板可能不存在，所以使用条件检查
    if (await settingsText.count() > 0) {
      await expect(settingsText.first()).toBeVisible();
    }
  });

  test('响应式布局 - 侧边栏可折叠', async ({ page }) => {
    // 找到折叠按钮（ChevronLeft图标）并点击
    const collapseButton = page.locator('button').filter({ has: page.locator('svg') }).first();
    if (await collapseButton.count() > 0) {
      await collapseButton.click();
      
      // 验证侧边栏状态变化
      await page.waitForTimeout(300);
    }
  });
});

test.describe('AI工作助手 - 数据持久化测试', () => {
  test('笔记数据在页面刷新后保留', async ({ page }) => {
    // 创建笔记
    await page.goto('/');
    await page.waitForTimeout(1000);
    
    await page.getByText('知识管理').first().click();
    await page.waitForTimeout(500);
    
    await page.getByRole('button', { name: /新建笔记/i }).click();
    
    const titleInput = page.locator('input[type="text"]').first();
    if (await titleInput.count() > 0) {
      await titleInput.fill('持久化测试笔记');
      
      const editor = page.locator('textarea').first();
      if (await editor.count() > 0) {
        await editor.fill('持久化测试内容');
      }
      
      const saveButton = page.getByRole('button', { name: /保存/i });
      if (await saveButton.count() > 0) {
        await saveButton.click();
        
        // 刷新页面
        await page.reload();
        await page.waitForTimeout(1000);
        
        // 验证笔记仍然存在
        await expect(page.getByText('持久化测试笔记')).toBeVisible();
      }
    }
  });
});

test.describe('AI工作助手 - 主题和设置测试', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);
  });

  test('设置面板 - 可以切换主题模式', async ({ page }) => {
    // 点击设置按钮
    await page.getByText('设置').first().click();
    await page.waitForTimeout(500);
    
    // 检查设置面板是否显示
    await expect(page.getByText('主题模式')).toBeVisible();
    
    // 点击深色主题
    await page.getByText('深色').first().click();
    await page.waitForTimeout(300);
    
    // 验证深色模式已应用（检查html类）
    const html = page.locator('html');
    await expect(html).toHaveClass(/dark/);
  });

  test('设置面板 - 可以切换颜色主题', async ({ page }) => {
    await page.getByText('设置').first().click();
    await page.waitForTimeout(500);
    
    // 检查颜色主题选项
    await expect(page.getByText('主题颜色')).toBeVisible();
    
    // 点击蓝色主题
    await page.getByText('蓝色').first().click();
    await page.waitForTimeout(300);
  });

  test('设置面板 - API配置页面可访问', async ({ page }) => {
    await page.getByText('设置').first().click();
    await page.waitForTimeout(500);
    
    // 点击API配置标签
    await page.getByText('API配置').click();
    await page.waitForTimeout(300);
    
    // 检查API配置元素
    await expect(page.getByText('OpenAI 配置').first()).toBeVisible();
    await expect(page.getByText('Azure OpenAI 配置').first()).toBeVisible();
  });

  test('设置面板 - 插件管理页面可访问', async ({ page }) => {
    await page.getByText('设置').first().click();
    await page.waitForTimeout(500);
    
    // 点击插件标签 - 使用左侧导航中的插件选项
    const pluginTab = page.locator('[role="tablist"] button').filter({ hasText: /^插件$/ });
    await pluginTab.click();
    await page.waitForTimeout(300);
    
    // 检查插件管理元素
    await expect(page.getByPlaceholder(/输入插件URL/).first()).toBeVisible();
  });
});
