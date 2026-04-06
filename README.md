# KAM

KAM 是一套 `local-first` 的软件工程 agent 工作台与控制面。
它不是聊天窗口外包一切，而是把工程工作显式化成一条可追踪、可比对、可继续推进的主链路：

`Task -> Refs -> Context Snapshot -> Runs -> Artifacts -> Review / Compare -> Follow-up Planning -> Dispatch / Continue`

它的目标不是“帮你问答”，而是“帮你把软件工程工作接住、做下去、让你能随时介入”。

## KAM 解决什么问题

真实的软件工程 agent 工作，难点通常不在单次生成，而在这些环节：

- 工作目标散落在聊天、PR、文档和代码里，不成任务对象
- agent 跑完之后只剩一段对话，不留下可复核的产物
- 一轮结果出来后，没人把它拆成下一轮可执行工作
- 任务一多就失控，不知道现在在干什么、卡在哪里、该不该重试
- 系统一旦中断，外部操作者不知道怎么恢复、打断、重启或接管

KAM 的产品设计就是围绕这些问题做的：让软件工程工作像一个可操作、可监督的任务系统一样运行，而不是像一次次临时对话。

## 适合谁

- 想在本机持续驱动 agent 干活的个人开发者
- 想把 PR 评论、改动建议、修复任务收进统一工作池的人
- 需要“自动继续推进”，但又必须保留人工干预与恢复能力的小团队

当前默认场景仍然是 `KAM builds KAM`，也就是先把这套系统在自身仓库上跑稳。

## 产品现在能做什么

### 1. 把工作显式化成任务

- 创建任务、维护任务状态、优先级、标签和依赖
- 给任务挂 refs，包括文件、仓库路径、PR、文档、外部链接
- 为任务生成 context snapshot，固定这一轮运行的上下文边界

### 2. 让 agent 执行变成可审计 run

- 基于任务启动 run，而不是直接在聊天里临时开工
- 保留 `stdout / summary / patch / changed_files / check_result` 等 artifacts
- 支持 `retry`、成功后的 `adopt`
- 支持在指定远端分支上起 worktree 执行并回推

### 3. 自动拆下一步工作

- 基于当前 task、snapshot、run、compare、artifacts 自动生成 follow-up tasks
- 子任务会自动带上推荐 prompt、建议 refs、验收检查项和推荐 agent
- 当前没有现成可跑 child task 时，可以先拆再跑

### 4. 自动继续推进，而不是只做单轮执行

- KAM 可以围绕当前 task family 自动决定下一步动作
- 当前动作集合包括：`adopt / retry / plan_and_dispatch / stop`
- 支持 task family 级别的 auto-drive
- 支持全局 backlog 级别的 auto-drive

### 5. 让外部操作者随时知道系统在干什么

- 提供统一 operator control plane
- 可以直接看到 focus task、attention items、推荐动作、近期事件
- 可以统一执行继续、接下一张、重试、采纳、打断 run、重启 supervisor
- 重启后会恢复持久化的全局无人值守状态，并把残留假活跃 run 收口

### 6. 把外部输入接进来

- PR review comments 可自动写入 KAM 任务池
- 同源评论在尚未执行前会刷新原任务，避免无意义并行
- 一旦已有 run，后续评论会进入新的后继任务，避免改写运行中上下文

## 真实使用方式

一个真实用户通常这样用 KAM：

1. 把一个工程目标、问题单、PR 评论或改进点放进任务池
2. 给它补 refs，让工作边界足够清晰
3. 让 KAM 生成 snapshot 并启动 run
4. 看结果产出的 artifacts、compare 和后续计划
5. 选择人工采纳、人工重试，或开启 auto-drive 让 KAM 继续推进
6. 在任何时候通过 operator control plane 观察状态、打断、重启或接管

这里的核心不是“AI 替你点一个按钮”，而是“整个工作过程有对象、有状态、有证据、有恢复语义”。

## 为什么它比纯脚本更像产品

KAM 不是一组零散脚本，而是一套有统一工作对象和控制平面的系统：

- UI 里能看到任务、refs、snapshot、run、compare、下一步计划
- CLI 里能看到当前 focus、attention、推荐动作和恢复入口
- 后端里有统一的任务、运行、artifact、autodrive 语义
- 文档里明确了打断、重启、恢复和人工介入边界

这意味着外部使用者不需要记住一堆内部脚本组合，只需要围绕“任务怎么进来、系统现在在做什么、我怎么干预”来使用它。

## 三分钟上手

如果你只是想在本机跑起来并开始值守：

1. 启动本地环境：`pwsh -File .\start-local.ps1`
2. 打开 operator 入口：`pwsh -File .\kam-operator.ps1 menu`
3. 做一轮本地验证：`pwsh -File .\verify-local.ps1`

启动后默认访问：`http://127.0.0.1:8000`

如果你想直接播种一套 demo harness 数据：

```powershell
pwsh -File .\seed-harness.ps1 -OpenBrowser
```

## 下载运行包

如果你不想在本机安装 Node，只想下载一个已经内置前端 `app/dist` 的运行包，可以直接用 GitHub Actions 构建出来的便携包。

解压后：

Windows：

```powershell
pwsh -ExecutionPolicy Bypass -File .\install.ps1
pwsh -File .\run.ps1
```

macOS / Linux：

```bash
bash ./install.sh
bash ./run.sh
```

运行包只要求 Python 3；不要求本机再执行 `npm install` 或 `npm run build`。

## 操作者入口

如果你平时主要从终端值守，优先用这些入口：

- `pwsh -File .\kam-operator.ps1 menu`
- `pwsh -File .\kam-operator.ps1 watch --interval-seconds 5`
- `pwsh -File .\kam-operator.ps1 status`
- `pwsh -File .\kam-operator.ps1 status --json`
- `pwsh -File .\kam-operator.ps1 status --fail-on-attention`
- `pwsh -File .\kam-operator.ps1 continue`
- `pwsh -File .\kam-operator.ps1 restart-global`
- `pwsh -File .\kam-operator.ps1 cancel`

其中：

- `menu` 适合人值守时快速选择推荐动作
- `watch` 适合盯盘，不适合交互恢复
- `status --json` 适合接脚本、监控、告警
- `restart-global` 适合系统重启、loop 异常或你明确要重拉 supervisor 时使用

更细的状态语义、打断与重启边界，直接看 [operator-control-plane.md](./docs/runbooks/operator-control-plane.md)。

## 当前默认配置

- 默认 agent：`codex`
- 可选 agent：`claude-code`
- 默认主门禁：`pwsh -NoProfile -File .\verify-local.ps1`
- 当前主产品入口：task-first workbench
- V3 workspace：已退场，不再是目标态

## 当前边界

KAM 当前明确不优先做这些方向：

- SaaS / 云化 / 多租户
- 账号体系
- 重型调度中心
- 大量连接器扩展
- 为历史兼容长期保留 V3 双主线

KAM 当前优先做的是：把“任务进入系统 -> agent 执行 -> 结果沉淀 -> 下一步继续 -> 人可接管”这条链路在真实仓库里跑硬。

## 本地开发

首次准备：

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r .\backend\requirements.txt
Set-Location .\app
npm install
Set-Location ..
```

开发常用命令：

```powershell
pwsh -File .\start-local.ps1
pwsh -File .\verify-local.ps1
```

如果你要额外验证默认 `codex` 的真实 agent 执行链路：

```powershell
pwsh -File .\verify-local.ps1 -RunRealAgentSmoke -RealSmokeAgent codex
```

如果你要验证可选的 `claude-code` lane：

```powershell
pwsh -File .\verify-local.ps1 -RunRealAgentSmoke -RealSmokeAgent claude-code
```

如果你要做更长时间的全局无人值守 soak：

```powershell
pwsh -File .\verify-local.ps1 -RunAutoDriveSoak -AutoDriveSoakMinutes 180
pwsh -File .\run-autodrive-soak.ps1 -Minutes 480 -TaskIntervalSeconds 30
```

## 验证命令

后端单测：

```powershell
.\.venv\Scripts\python.exe -m unittest backend.tests.test_db_init -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_harness_api -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_task_planner_api -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_run_engine_lore -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_github_adapter -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_pr_review_monitor -v
.\.venv\Scripts\python.exe -m unittest backend.tests.test_operator_cli -v
```

前端：

```powershell
Set-Location app
npm run build
npm run lint
npm run test:smoke:local
npm run test:smoke:agent
npm run test:soak:autodrive
```

## 参考文档

- [docs/README.md](./docs/README.md)
- [docs/product/ai_work_assistant_prd.md](./docs/product/ai_work_assistant_prd.md)
- [docs/runbooks/operator-control-plane.md](./docs/runbooks/operator-control-plane.md)
- [docs/roadmap/v3_delivery_status.md](./docs/roadmap/v3_delivery_status.md)
- [.omx/plans/prd-harness-dogfood-cutover.md](./.omx/plans/prd-harness-dogfood-cutover.md)
- [.omx/plans/test-spec-harness-dogfood-cutover.md](./.omx/plans/test-spec-harness-dogfood-cutover.md)
