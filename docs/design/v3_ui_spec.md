# KAM v2 — UI 设计规范

> 核心原则：用户唯一的操作是打字。界面只展示"需要你关注的事"。
> 所有配置、路由、调度由 AI 在幕后完成。

---

## 1. 设计哲学

### 1.1 三条铁律

1. **对话是唯一入口。** 不要配置表单，不要设置页面。创建 Project、选择 Agent、配置 Watcher——全部通过对话完成。
2. **AI 结果用人话展示。** 用户看到的是"修复了 token 刷新逻辑，改了 3 个文件，测试通过"，不是 `Run c7287c | Passed | round 1/5 | 1.3s`。
3. **只展示需要决策的信息。** File tree、repo 路径、PowerShell 命令——这些是调试信息，不是用户需要的。用户需要的是：做了什么、结果如何、下一步是什么。

### 1.2 "外置大脑" vs "控制中心" 的矛盾

"大脑"是隐形的——它让你觉得"它就是知道"。
"控制中心"是显性的——它让你觉得"我需要配置和管理"。

**先做好大脑。** 等产品成熟了再逐步暴露控制中心的能力给高级用户。

### 1.3 视觉风格

- **深色主题为主**（与代码编辑器一致），支持亮色切换
- **扁平、无阴影、无渐变**。用颜色和间距区分层级
- **边框 0.5px**，圆角 8-12px
- **字体**：系统无衬线体（-apple-system, Segoe UI）
- **信息密度**：中等偏高。开发者不需要大留白

---

## 2. 布局架构

### 2.1 三栏结构

```
┌────────────┬──────────────────────────┬─────────────┐
│            │                          │             │
│  Sidebar   │     Main Area            │   Memory    │
│  220px     │     flex: 1              │   280px     │
│  固定       │     对话 或 Home         │   默认隐藏   │
│            │                          │   滑入面板   │
│            │                          │             │
└────────────┴──────────────────────────┴─────────────┘
```

- **Sidebar（左）**：220px 固定宽度。展示对话历史，按项目分组。底部有 Home 和 Watcher 入口。
- **Main Area（中）**：弹性宽度。三种视图状态：Empty → Home feed → Thread conversation。
- **Memory Panel（右）**：280px，默认隐藏。点击触发滑入动画（0.25s ease）。展示 AI 的记忆。

### 2.2 顶部栏

高度 44-48px。内容：

- **左侧**：面包屑导航。格式 `项目名 / Thread 标题`。空状态显示 `New conversation`。
- **右侧**：Memory 按钮（点击切换右侧面板）。

不要放：
- 页面标题（面包屑已经说明了位置）
- 统计数字（0 Runs / 0 Sessions 等）
- 状态栏

---

## 3. Sidebar 设计

### 3.1 结构

```
┌──────────────────┐
│  [Logo] KAM      │  ← 品牌标识
├──────────────────┤
│  ● 2 tasks running │  ← Active 聚合入口（点击进入 Home）
├──────────────────┤
│  NOISE PROBE     │  ← 项目分组标签
│  ● Fix login...  │  ← Thread 条目
│  ● Add digest... │
│                  │
│  ROADMAP QA      │
│  ● Expand test.. │
│  ○ Review API... │
├──────────────────┤
│  [Home] [Watcher] │  ← 底部固定操作
└──────────────────┘
```

### 3.2 Thread 条目

每个 Thread 条目包含：
- **状态圆点**（7px）：颜色编码当前状态
- **标题**：AI 生成的 thread 标题（不是用户手填的）
- **副信息**：时间或状态描述（"2 min ago" / "Running..." / "Passed, waiting to adopt"）

### 3.3 状态圆点颜色

| 颜色 | Hex | 含义 |
|------|-----|------|
| 橙色 | `#c87a3c` | 正在运行（Run running 或 Watcher 有新事件） |
| 绿色 | `#5dca7a` | 完成，等待决策（Run passed 未 adopt） |
| 红色 | `#e24b4a` | 失败，需要关注 |
| 灰色 | `#5f5e5a` | 历史 / 非活跃 |
| 紫色 | `#7f77dd` | Watcher 相关 |

### 3.4 Active 聚合入口

Sidebar 顶部的特殊条目。显示当前活跃任务数量（"2 tasks running" / "3 items need attention"）。
点击进入 Home feed。当有新事件时文字变为橙色。

### 3.5 项目分组

- Thread 按所属 Project 自动分组
- 分组标签：11px 大写字母，#73726c 颜色
- 不需要独立的 "Projects" 列表
- Project 由 AI 在用户首次提到工作时自动创建

### 3.6 删除的元素

以下内容从旧版删除，不需要替代品：
- "New project" 按钮 → AI 自动创建
- "New thread" 输入框 → 在主区域输入框开始新对话
- COMMAND / PROJECTS / THREADS / RUNS 导航标签
- 竖栏圆点导航

---

## 4. Main Area — 三种视图

### 4.1 Empty State（空状态）

用户第一次打开 KAM，或点击 "New"。

```
┌─────────────────────────────────────┐
│                                     │
│                                     │
│            [+] 图标                  │
│                                     │
│     What are you working on?        │
│                                     │
│  Describe your task or paste a      │
│  repo path. KAM will figure out     │
│  the rest.                          │
│                                     │
│                                     │
├─────────────────────────────────────┤
│  [输入框                        🔘]  │
│  ● Claude Code        Auto-detected │
└─────────────────────────────────────┘
```

设计要点：
- 图标：48x48px 圆角方形，内部 "+" 号
- 标题：18px，font-weight 500
- 提示文字：13px，#73726c，居中，最大宽度 300px
- 输入框始终在底部固定
- Agent 标签 "Claude Code" 在输入框下方，是信息展示不是下拉选择

### 4.2 Home Feed（任务总览）

用户有多个并行任务时的首页。从 Sidebar 的 Active 入口或 Home 按钮进入。

#### 顶部问候

```
Good afternoon
2 tasks running, 1 watcher alert, 1 task waiting to adopt.
```

- 问候语：18px，font-weight 500
- 副信息：13px，#73726c

#### 三层优先级

**第一层：Needs your attention**

混排两种卡片：
1. **完成的 Run**（等待 adopt 或 failed）
2. **Watcher 事件**（新 PR 评论、CI 失败、新任务等）

Watcher 事件卡片用左侧 3px 紫色边框区分。

**第二层：Running in background**

正在执行的 Run。展示进度条和当前步骤描述。

**第三层：Recent**

最近完成的历史。半透明（opacity: 0.6）。

#### 分区标签

```
NEEDS YOUR ATTENTION
─────────────────────
```

11px 大写，#73726c，letter-spacing 0.5px，font-weight 500

### 4.3 Thread Conversation（对话视图）

从 Sidebar 点击某个 Thread 进入。

#### 消息布局

```
┌──────────────────────────────────────────┐
│                                          │
│     ┌──────────────────────┐             │
│     │ Login timeout after  │  ← 用户消息  │
│     │ 30s. Fix this.       │    右对齐     │
│     └──────────────────────┘    圆角不同   │
│                                          │
│  Got it. I can see from our last         │
│  session you're using JWT...             │
│                                    ← AI  │
│  ┌────────────────────────────────────┐  │
│  │ ● Fixed token refresh logic  1.3s │  │
│  │                                    │  │
│  │ Updated the Axios interceptor...  │  │
│  │ [auth.ts] [interceptor.ts]        │  │
│  │ ✓ 3 tests passed                 │  │
│  │                                    │  │
│  │ [View diff] [Logs] [■ Adopt]      │  │
│  └────────────────────────────────────┘  │
│                                          │
│  Done. Want me to adopt these changes?   │
│                                          │
├──────────────────────────────────────────┤
│  [输入框                            🔘]  │
│  ● Claude Code            Auto-detected  │
└──────────────────────────────────────────┘
```

#### 消息样式

**用户消息：**
- 右对齐（align-self: flex-end）
- 背景 #2c2b28
- 圆角 14px 14px 4px 14px（右下角收窄）
- 最大宽度 440px
- 字号 14px

**AI 消息：**
- 左对齐（align-self: flex-start）
- 无背景（直接放文字）
- 最大宽度 480px
- 字号 14px，行高 1.6

**Run 卡片：** 嵌在对话流中（align-self: stretch），详见第 5 节。

---

## 5. Run Card 设计

### 5.1 核心原则

Run 卡片展示的是 **AI 消化后的结果**，不是系统原始输出。

对比：
| Before（旧） | After（新） |
|---|---|
| Run c7287c | Fixed token refresh logic |
| PowerShell 命令全文 | 不显示 |
| "digest probe ok" | "Updated interceptor, added mutex, 3 tests pass" |
| 查看 Diff / 日志 / 重试 | View diff / Logs / **Adopt changes** |

### 5.2 四种状态

#### Pending（等待中）

```
┌──────────────────────────────────────┐
│ ○ Queued                     Pending │
│                                      │
│ Task: Fix the token refresh          │
│ interceptor to handle 401s           │
└──────────────────────────────────────┘
```

- 圆点颜色：#73726c（灰色）
- 边框：默认 #3d3c38
- 无操作按钮

#### Running（执行中）

```
┌──────────────────────────────────────┐
│ ● Fixing token refresh...    Running │
│                                      │
│ Reading auth.ts and interceptor.ts   │
│ ████████████░░░░░░░░                 │
└──────────────────────────────────────┘
```

- 圆点颜色：#c87a3c（橙色）
- 边框颜色：border-color 带橙色
- 进度描述：11px，#c87a3c
- 进度条：3px 高，背景 #2c2b28，填充 #c87a3c，动画 ease-in-out

进度条动画 CSS：
```css
@keyframes progress {
  0%, 100% { width: 35% }
  50% { width: 80% }
}
```

#### Passed（通过）

```
┌──────────────────────────────────────┐
│ ● Fixed token refresh logic    1.3s  │
│                                      │
│ Updated the Axios interceptor to     │
│ catch 401s, refresh token, retry.    │
│ Added mutex for concurrent refresh.  │
│                                      │
│ [auth.ts] [interceptor.ts]           │
│ [auth.test.ts]                       │
│ ✓ 3 tests passed                     │
├──────────────────────────────────────┤
│ [View diff] [Logs]  [■ Adopt changes]│
└──────────────────────────────────────┘
```

- 圆点颜色：#5dca7a（绿色）
- 边框颜色：rgba(93,202,122,0.3)
- 标题：AI 生成的任务描述（不是 Run ID）
- 时间：右上角，11px，#73726c
- 正文：AI 生成的结果摘要，12px，#a09e96
- 文件标签：背景 #2c2b28，mono 字体，10px
- 测试结果：11px，#5dca7a
- **Adopt changes 是 primary 按钮**（橙色背景 #c87a3c，白字）
- View diff / Logs 是次级按钮（边框灰色，无背景）

#### Failed（失败）

```
┌──────────────────────────────────────┐
│ ● Token refresh fix failed     4.2s  │
│                                      │
│ Test auth.test.ts:42 failed:         │
│ refresh endpoint returned 403.       │
│                                      │
│ Likely cause: the refresh endpoint   │
│ expects a different header format.   │
├──────────────────────────────────────┤
│ [View logs] [Retry] [Let me explain] │
└──────────────────────────────────────┘
```

- 圆点颜色：#e24b4a（红色）
- 边框颜色：rgba(226,75,74,0.3)
- 失败原因：12px，#e24b4a
- 建议下一步：12px，#a09e96
- "Let me explain more" 按钮：让用户补充上下文后重试

### 5.3 操作按钮规范

| 按钮 | 类型 | 样式 |
|------|------|------|
| Adopt changes | Primary | 背景 #c87a3c，白字，无边框 |
| Apply fix + reply | Primary (green) | 背景 #1d9e75，白字 |
| View diff / Logs | Secondary | 边框 #3d3c38，无背景，#a09e96 文字 |
| Retry / Let me explain | Secondary | 同上 |

按钮高度 28px，圆角 6px，字号 11px，内边距 4px 10px。

---

## 6. Home Feed 卡片设计

### 6.1 普通任务卡片

与 Run Card 的 Passed/Failed 状态相同，但加入项目名标签。

```
┌──────────────────────────────────────┐
│ ● Fixed token refresh logic  Passed  │
│ Noise Probe · 20 min ago             │
│                                      │
│ Fixed Axios interceptor. 3 files,    │
│ all tests pass.                      │
│                                      │
│ [View diff]  [■ Adopt changes]       │
└──────────────────────────────────────┘
```

### 6.2 Watcher 事件卡片

左侧 3px 紫色 (#7f77dd) 边框。标题前有 Watcher 图标。右上角有来源标签。

```
┌──────────────────────────────────────┐
│ │ [W] 3 new work items      Azure DevOps │
│ │ Watcher: DevOps task sync · 5m ago │
│ │                                    │
│ │ #4521 Implement SSO        High    │
│ │ #4518 Fix memory leak      Critical│
│ │ #4515 Add rate limiting    Medium  │
│ │                                    │
│ │ [Start #4518] [Analyze all] [■ Plan│
│ │  my sprint]                        │
└──────────────────────────────────────┘
```

设计要点：
- 左边框：3px solid #7f77dd，卡片左侧圆角为 0（border-radius: 0 12px 12px 0）
- Watcher 图标：28px 圆角方形，背景色按类型：紫色(#7f77dd)=通用，红色(#e24b4a)=CI 失败，灰色(#888780)=扫描
- 来源标签：10px，背景 #2c2b28，内含 5px 圆点 + 文字
- 操作按钮根据事件类型动态生成（不固定）

### 6.3 CI 失败卡片

```
┌──────────────────────────────────────┐
│ │ [C] CI failed on main    CI pipeline│
│ │ Watcher: CI monitor · 12 min ago   │
│ │                                    │
│ │ Build #892 failed at test stage.   │
│ │ AI analysis: auth.test.ts expects  │
│ │ 200 but middleware returns 204.    │
│ │ Likely PR #231.                    │
│ │                                    │
│ │ [View full analysis] [■ Auto-fix]  │
└──────────────────────────────────────┘
```

### 6.4 Running 卡片（后台执行中）

```
┌──────────────────────────────────────┐
│ ● Add digest endpoint        Running │
│ Noise Probe                          │
│                                      │
│ Writing run_engine.py digest...      │
│ ████████░░░░░░░░░░░░                 │
└──────────────────────────────────────┘
```

无操作按钮。进度条动画同 Run Card Running 状态。

### 6.5 历史卡片

```
┌──────────────────────────────────────┐
│ ○ Review API contracts               │  ← opacity: 0.6
│ Roadmap QA · Yesterday               │
└──────────────────────────────────────┘
```

精简展示，无正文，无操作按钮。

---

## 7. PR Review 界面

### 7.1 场景描述

Watcher 检测到 PR 有新 review comment → AI 分析每条评论 → 分类为 "needs your input" 或 "AI can fix" → 展示在 Thread 对话流中。

### 7.2 Review Comment 卡片

```
┌──────────────────────────────────────┐
│ [头像] Chen      Needs your input     │
│                           auth.ts:42  │
├──────────────────────────────────────┤
│ "Why not use axios-retry instead     │
│ of manual implementation?"           │
├──────────────────────────────────────┤
│ AI DRAFT REPLY                       │
│                                      │
│ We considered axios-retry, but it    │
│ doesn't support selective retry...   │
├──────────────────────────────────────┤
│ [Edit reply]  [■ Post this reply]    │
└──────────────────────────────────────┘
```

#### 卡片结构

**Header（头部）：**
- Reviewer 头像：22px 圆形，紫色背景 (#534AB7)，白字首字母
- Reviewer 名字：12px，font-weight 500
- 分类标签：
  - "Needs your input" — 背景 rgba(200,122,60,0.15)，文字 #c87a3c
  - "AI can fix" — 背景 rgba(93,202,122,0.15)，文字 #5dca7a
- 文件位置：右对齐，11px，mono 字体，#73726c

**Comment（评论原文）：**
- 12px，#a09e96，行高 1.6
- 背景无，上下有 0.5px 分隔线

**AI Response（AI 预处理）：**
- 标签 "AI DRAFT REPLY" 或 "AI FIX READY"：10px 大写，#c87a3c，font-weight 500
- 内容：12px，#e8e6df（比评论原文更亮，因为这是 AI 生成的建议）
- 如果是代码修复：包含代码块（背景 #2c2b28，mono 字体 11px）

**Actions（操作）：**
- "Needs your input" 卡片：[Edit reply] [Post this reply]
- "AI can fix" 卡片：[View full diff] [Edit fix] [Apply fix + reply "Fixed"]
- "Apply fix + reply" 用绿色 primary 按钮：背景 #1d9e75

### 7.3 整体对话流

```
[AI message] Chen reviewed your PR with 3 comments.
             I've read all of them against your code.
             Here's my triage:

[Review Card] Comment 1 — needs your input
[Review Card] Comment 2 — AI can fix
[Review Card] Comment 3 — AI can fix

[AI message] Summary: 1 needs your judgment,
             2 I can fix right now. Want me to
             apply both fixes?

[User message] Yes, apply both fixes...

[AI message] Got it. Applying now...
```

---

## 8. Memory Panel

### 8.1 触发方式

- 点击顶部栏 "Memory" 按钮
- 点击 Sidebar 底部 "Memory" 按钮
- 面板从右侧滑入，width 从 0 过渡到 280px，duration 0.25s ease

### 8.2 内容结构

```
┌────────────────────────┐
│ AI memory              │
│ What KAM knows about   │
│ this project           │
│                        │
│ PREFERENCES            │
│ ┌────────────────────┐ │
│ │ Testing: Always    │ │
│ │ run vitest before  │ │
│ │ marking done       │ │
│ └────────────────────┘ │
│ ┌────────────────────┐ │
│ │ Style: Prefers     │ │
│ │ functional comps   │ │
│ └────────────────────┘ │
│                        │
│ DECISIONS              │
│ ┌────────────────────┐ │
│ │ Auth: JWT + 30min  │ │
│ │ expiry + refresh   │ │
│ │ (decided Mar 20)   │ │
│ └────────────────────┘ │
│                        │
│ PROJECT CONTEXT        │
│ ┌────────────────────┐ │
│ │ Stack: React +     │ │
│ │ Vite + tRPC        │ │
│ └────────────────────┘ │
│ ┌────────────────────┐ │
│ │ Repo: D:\Repos\KAM │ │
│ └────────────────────┘ │
└────────────────────────┘
```

### 8.3 记忆条目样式

- 背景 #2c2b28，圆角 8px，内边距 8px 10px
- 类别标签加粗（font-weight 500，#e8e6df）
- 内容 12px，#a09e96，行高 1.5
- 分区标签：同 Home feed 分区标签（11px 大写灰色）

### 8.4 展示内容（按分区）

| 分区 | 展示内容 | 来源 |
|------|---------|------|
| Preferences | 用户偏好（测试框架、代码风格、命名规范） | AI 自动从对话中提取 |
| Decisions | 架构/技术决策 + 时间 + 原因 | AI 自动从对话中提取 |
| Project context | 技术栈、Repo 路径、上次 Run 状态 | 自动检测 + 对话 |

### 8.5 不展示的内容

- File tree（降级为 Project context 下的一行 "Repo: path"）
- Settings / Edit settings 按钮
- Active Runs（在 Home feed 和 Thread 里已经展示了）
- Pinned Resources（不需要手动 pin，AI 自动判断相关性）

---

## 9. 输入框设计

### 9.1 结构

```
┌──────────────────────────────────────┐
│  [文本输入区域                   🔘]  │
├──────────────────────────────────────┤
│  ● Claude Code          Auto-detected│
└──────────────────────────────────────┘
```

### 9.2 样式

- 外框：背景 #242320，边框 0.5px #3d3c38，圆角 12px
- Focus 状态：边框变为 #c87a3c
- Textarea：无背景，无边框，14px，行高 1.5
- Placeholder："Describe what you need..." / "Reply..."
- 发送按钮：32px 圆形，背景 #c87a3c，白色箭头图标

### 9.3 Agent 标签

- 位置：输入框下方，左侧
- 圆点 + 文字："● Claude Code"
- 右侧说明："Auto-detected"
- Agent 由 AI 自动选择，用户通常不需要改
- 点击标签可以手动覆盖（高级操作，不突出）

### 9.4 Empty State 中的输入框

与 Thread 中的输入框完全相同，只是 placeholder 不同：
- Empty state："Describe what you need..."
- Thread："Reply..."

---

## 10. Toast 通知

### 10.1 场景

用户在某个 Thread 的对话中工作，另一个后台任务完成了。底部浮现 Toast。

### 10.2 样式

```
┌─────────────────────────────────────┐
│  ● Add digest endpoint just finished  View │
└─────────────────────────────────────┘
```

- 位置：Main Area 底部居中，距输入框上方 20px
- 背景 #242320，边框 0.5px #3d3c38，圆角 10px
- 内容：状态圆点 + 任务名 + "just finished" + "View" 链接
- 点击 → 跳转到该任务的 Home feed 条目
- 自动消失：10 秒后淡出（或用户点击后立即消失）

### 10.3 不触发 Toast 的情况

- 当前正在查看 Home feed（事件直接刷新 feed）
- Watcher 事件中 status=dismissed 的
- LGTM / resolved 等无需关注的 PR 评论

---

## 11. Watcher 管理界面

### 11.1 入口

Sidebar 底部 "Watchers" 按钮，或 Sidebar 中 "3 active watchers" 条目。

### 11.2 Watcher 列表

```
┌──────────────────────────────────────┐
│  Watchers · 3 active                 │
│  AI monitors these sources in the    │
│  background and surfaces events      │
│  on your Home feed.                  │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ [W] DevOps task sync   Active│    │
│  │ Azure DevOps · Every 15 min │    │
│  │ Last: 5 min ago              │    │
│  │                              │    │
│  │ Watches for new work items   │    │
│  │ assigned to you...           │    │
│  │                              │    │
│  │ [Edit] [Pause] [View history]│    │
│  └──────────────────────────────┘    │
│                                      │
│  ┌──────────────────────────────┐    │
│  │ [C] CI failure monitor Active│    │
│  │ GitHub Actions · On push     │    │
│  │ Last: 12 min ago             │    │
│  │ ...                          │    │
│  └──────────────────────────────┘    │
│                                      │
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐   │
│  │ Tell AI what to watch to add │    │
│  │ a new watcher...             │    │
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┘   │
└──────────────────────────────────────┘
```

### 11.3 Watcher 卡片

- 图标：28px 圆角方形，颜色按类型
- 标题 + Active/Paused 标签
- 来源 + 频率 + 上次运行时间
- 描述：12px，#a09e96
- 操作：Edit / Pause(Resume) / View history / Run now

### 11.4 添加新 Watcher

**不是表单。** 底部的虚线框点击后跳转到新对话，用户用自然语言描述想监控什么，AI 生成 Watcher 配置卡片（在对话中展示），用户确认激活。

### 11.5 Watcher 配置卡片（对话内）

当 AI 调用 create_watcher tool 后，在对话中展示确认卡片：

```
┌──────────────────────────────────────┐
│  [W] DevOps task sync                │
│  New watcher                         │
├──────────────────────────────────────┤
│  Source: Azure DevOps, board "KAM"   │
│  Trigger: New work item assigned     │
│  Frequency: Every 15 minutes         │
│  Action: Read, analyze, summarize    │
├──────────────────────────────────────┤
│  [Edit details]  [■ Activate watcher]│
└──────────────────────────────────────┘
```

---

## 12. 自动化等级指示器

### 12.1 概念

每个 Watcher 有 auto_action_level（0-3）。UI 上不用数字，用人话标签：

| Level | 标签 | 含义 |
|-------|------|------|
| 0 | Notify only | 只通知，不做任何处理 |
| 1 | Triage + draft | AI 分类、草拟回复/修复，你确认后执行（默认） |
| 2 | Auto-fix | 客观修复自动执行，主观问题才问你 |
| 3 | Full autopilot | 全自动处理 |

### 12.2 展示位置

Watcher 管理界面的 Edit 模态中。不在主界面暴露——大部分用户用 Level 1 就够了。

---

## 13. 响应式行为

### 13.1 窄屏（<1024px）

- Sidebar 折叠为图标栏（60px 宽，只显示头像和状态圆点）
- Memory panel 变为全屏覆盖
- 主区域占满剩余空间

### 13.2 宽屏（>1440px）

- 主区域内容最大宽度 720px，居中
- Sidebar 和 Memory panel 宽度不变

---

## 14. 颜色系统

### 14.1 基础色

| 用途 | 变量名 | 深色值 |
|------|--------|--------|
| 主背景 | --bg | #1a1918 |
| 表面/卡片背景 | --bg2 | #242320 |
| 凹陷/代码块/标签 | --bg3 | #2c2b28 |
| 边框 | --border | #3d3c38 |
| 主文字 | --t1 | #e8e6df |
| 次文字 | --t2 | #a09e96 |
| 弱文字/placeholder | --t3 | #73726c |

### 14.2 语义色

| 用途 | 变量名 | 值 |
|------|--------|-----|
| 品牌/主操作 | --accent | #c87a3c |
| 成功/通过 | --green | #5dca7a |
| 失败/错误 | --red | #e24b4a |
| Watcher/记忆 | --purple | #7f77dd |
| 正在运行 | --running | #c87a3c（同 accent）|

### 14.3 使用规则

- 状态圆点颜色必须使用语义色
- Primary 按钮背景使用 --accent，文字白色
- 链接和可点击文字使用 --t1（不要蓝色下划线）
- 边框统一 0.5px --border
- 不使用渐变、阴影、发光效果

---

## 15. 动效规范

| 效果 | 时长 | 缓动 | 触发 |
|------|------|------|------|
| Sidebar 项 hover | 0.15s | ease | 鼠标进入 |
| Memory panel 展开 | 0.25s | ease | 点击 Memory 按钮 |
| Toast 淡入 | 0.3s | ease | 后台任务完成 |
| Toast 淡出 | 0.3s | ease | 10 秒后或点击 |
| 输入框 focus 边框 | 0.15s | ease | 获得焦点 |
| Run 进度条 | 2s | ease-in-out | 循环动画（@keyframes） |
| 按钮 active | - | - | transform: scale(0.98) |

所有动画应支持 `prefers-reduced-motion` 媒体查询。

---

## 16. 实现优先级

### P0：先删后加

从现有界面删除以下元素（无需替代品）：
- "New project" 弹窗和按钮
- COMMAND / PROJECTS / THREADS / RUNS 导航
- LOOK 按钮
- 左侧栏输入框（新项目标题、新线程标题）
- "KAM 对话区" 标题和所有副标题
- 零值统计标签（0 Runs / 0 Compare Sessions）
- "发送时自动创建 Run" 勾选框
- "带去对比" 按钮
- Status 栏
- 技术术语说明段落
- Context 面板中的 Settings / File Tree / Pinned Resources

### P1：核心重构

1. 三栏布局（Sidebar + Main + Memory panel）
2. 空状态（图标 + "What are you working on?" + 输入框）
3. Thread 对话视图（消息气泡 + Run 卡片）
4. Run 卡片四种状态
5. Sidebar 状态圆点 + 按项目分组
6. 面包屑导航

### P2：完整体验

1. Home feed（三层优先级）
2. Toast 通知
3. Memory panel
4. PR review 卡片
5. Watcher 管理界面
6. Watcher 配置卡片（对话内）

---

## 17. 组件文件映射

| 组件 | 文件 | 对应本文档章节 |
|------|------|--------------|
| AppShell | layout/AppShell.tsx | §2 布局架构 |
| Sidebar | layout/Sidebar.tsx | §3 Sidebar |
| HomeFeed | features/home/HomeFeed.tsx | §4.2 + §6 |
| ThreadView | features/thread/ThreadView.tsx | §4.3 |
| MessageBubble | features/thread/MessageBubble.tsx | §4.3 消息样式 |
| MessageInput | features/thread/MessageInput.tsx | §9 输入框 |
| RunCard | features/thread/RunCard.tsx | §5 Run Card |
| ReviewCommentCard | features/review/ReviewCommentCard.tsx | §7 PR Review |
| MemoryPanel | features/memory/MemoryPanel.tsx | §8 Memory |
| WatcherList | features/watcher/WatcherList.tsx | §11 Watcher 管理 |
| Toast | layout/Toast.tsx | §10 Toast |
| useSSE | hooks/useSSE.ts | 技术设计文档 §9.1 |
| useSendMessage | hooks/useSendMessage.ts | 技术设计文档 §9.2 |

---

*设计规范完成于 2026-03-27。与技术设计文档 (KAM_V2_DESIGN.md) 配套使用。*
