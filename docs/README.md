# 文档索引

当前仓库的主目标已经切到 `task-first software-engineering harness`，并且当前主链路已经进入：

`Task -> Refs -> Context Snapshot -> Runs -> Artifacts -> Review / Compare -> Follow-up Planning -> Next-Task Dispatch -> Continue / Auto-Drive`

## 当前主参考

- [../README.md](../README.md): 仓库根说明、本地启动、最常用 operator 入口
- [runbooks/operator-control-plane.md](runbooks/operator-control-plane.md): 本机值守 / 外部操作者状态查看、重触发、打断、重启手册
- [roadmap/v3_delivery_status.md](roadmap/v3_delivery_status.md): 当前交付状态、已完成能力和剩余缺口
- [product/ai_work_assistant_prd.md](product/ai_work_assistant_prd.md): 当前唯一产品目标定义
- [../.omx/plans/prd-harness-dogfood-cutover.md](../.omx/plans/prd-harness-dogfood-cutover.md): 本地 cutover PRD
- [../.omx/plans/test-spec-harness-dogfood-cutover.md](../.omx/plans/test-spec-harness-dogfood-cutover.md): 本地 cutover test spec

## 按角色查看

- 如果你是第一次在本机把 KAM 跑起来：先看 [../README.md](../README.md)
- 如果你是本机值守或要人工恢复一轮：先看 [runbooks/operator-control-plane.md](runbooks/operator-control-plane.md)
- 如果你想判断“现在做到哪一步、还差什么”：先看 [roadmap/v3_delivery_status.md](roadmap/v3_delivery_status.md)
- 如果你要对齐产品目标，而不是当前实现细节：看 [product/ai_work_assistant_prd.md](product/ai_work_assistant_prd.md)

当前新增的最小自动闭环能力也以这组文档为准：

- `POST /api/tasks/continue`
- `POST /api/tasks/{task_id}/autodrive/start`
- `POST /api/tasks/{task_id}/autodrive/stop`
- `GET /api/operator/control-plane`
- `POST /api/operator/actions`
- `pwsh -File .\kam-operator.ps1 ...`
- `pwsh -File .\kam-operator.ps1 menu`
- UI 的“操作台”
- 当前动作集合：`adopt / retry / plan_and_dispatch / stop`
- 当前范围：既支持选中 `task family` 的自动托管，也支持全局任务池调度与 supervisor 重启

## 过渡与历史资料

- [design/v3_architecture_design.md](design/v3_architecture_design.md): V3 设计稿，已降级为历史参考
- [design/v3_ui_spec.md](design/v3_ui_spec.md): V3 UI 规范，已降级为历史参考
- [roadmap/v2_implementation_roadmap.md](roadmap/v2_implementation_roadmap.md): 历史执行拆解
- [roadmap/mvp_backlog.md](roadmap/mvp_backlog.md): 历史 backlog
- [migration/](migration): 历史迁移文档

## 历史归档

- [archive/legacy/](archive/legacy): 历史方案，不再作为当前实现依据
- [archive/notes/](archive/notes): 调试探针和临时记录
