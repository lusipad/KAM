# KAM v2 Backlog

## Now

- 用 SSE 替换部分高频轮询，补齐 Run / Thread 实时事件流
- 给 Compare 面板增加更细的差异摘要与 artifacts 横向对照
- 补充 Project file tree 与 pinned resources 的文件侧导航体验
- 让 Router 的 LLM 路由从 JSON 分类继续演进到更稳定的 function calling

## Next

- 为 Memory 增加可编辑 learnings 与 decision 修订能力
- 给 Project 增加模板化 `checkCommands` 与 agent presets
- 补齐更清晰的 system event 消息卡片
- 为 custom command 提供更强的参数模板与校验

## Later

- 基于 embedding 的 learnings 语义检索
- 按 Project 维度沉淀长期知识图谱
- 更强的 Run compare diff 视图
- 对 Thread 历史做自动摘要压缩与归档

## Legacy

- Lite Core 与旧自治链路保留在仓库中，仅作为迁移兼容与历史参考
- 当 v2 主链路完全覆盖后，可进一步移入 `docs/archive/legacy/` 对应范围的维护模式
