# AI工作助手

一个面向开发内用的工作助手，定位是“外置大脑 + Agent 指挥台”。它负责承接任务、沉淀上下文、管理笔记，并并发调度多个外部 Agent（如 Codex、Claude Code）执行工作，再把结果统一收口给人判断。

> 当前仓库的设计方向已收敛到 Lite 架构，部分代码和 API 仍在向该方向持续调整中。

## 功能特性

### 1. 收件箱与任务台
- 记录任务、想法、会议结论、链接和资料
- 任务卡状态流转与优先级管理
- Markdown 笔记与任务关联

### 2. 上下文与轻量记忆
- 关联 ADO、Git、文档和历史笔记
- 保存任务上下文快照与对话摘要
- 优先使用全文检索，向量检索按需启用

### 3. Agent 指挥台
- 并发调度多个外部 Agent
- 管理运行状态、日志、diff 和总结
- 支持隔离工作目录和结果比较

### 4. 开发系统集成
- Azure DevOps 工作项、PR、构建状态读取
- 仓库和文档引用
- 手动刷新上下文，不依赖复杂同步链路

### 5. 结果收口
- 汇总多个 Agent 的产物
- 生成风险说明和下一步建议
- 人工做最终采纳和决策

## 技术架构

### 前端
- React 18 + TypeScript
- Vite构建工具
- Tailwind CSS + shadcn/ui组件库
- Zustand状态管理
- Axios HTTP客户端

### 后端
- FastAPI (Python 3.11)
- SQLAlchemy ORM
- Pydantic数据验证
- 外部 Agent CLI 适配

### 数据库
- PostgreSQL 15（主存储）
- Redis（可选，用于缓存和轻量队列）
- pgvector（可选，用于文档问答增强）

## 本地启动

### 前提条件
- Docker和Docker Compose
- OpenAI API密钥

### 启动步骤

1. 克隆代码到本地
2. 设置环境变量
```bash
export OPENAI_API_KEY=your-openai-api-key
```

3. 启动所有服务
```bash
cd KAM
docker-compose up -d
```

4. 访问应用
- 前端: http://localhost
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

### 服务端口
- 前端: 80
- 后端API: 8000
- PostgreSQL: 5432
- Redis: 6379

## 项目结构

```
/mnt/okcomputer/output/
├── app/                    # 前端React应用
│   ├── src/
│   │   ├── components/     # UI组件
│   │   ├── store/          # 状态管理
│   │   ├── lib/            # API客户端
│   │   └── types/          # TypeScript类型
│   └── dist/               # 构建输出
├── backend/                # 后端FastAPI服务
│   ├── app/
│   │   ├── api/            # API路由
│   │   ├── models/         # 数据库模型
│   │   ├── services/       # 业务逻辑
│   │   └── core/           # 配置文件
│   └── alembic/            # 数据库迁移
├── docker-compose.yml      # Docker编排配置
└── README.md               # 本文件
```

## API端点

> 当前代码中的 API 仍保留早期实现结构；Lite 方向的目标 API 设计请参考 `system_architecture.md`。

### 笔记管理
- `GET /api/notes` - 获取笔记列表
- `POST /api/notes` - 创建笔记
- `PUT /api/notes/{id}` - 更新笔记
- `DELETE /api/notes/{id}` - 删除笔记

### 记忆管理
- `GET /api/memories` - 获取记忆列表
- `POST /api/memories` - 创建记忆
- `GET /api/memories/search` - 搜索记忆

### ClawTeam
- `GET /api/clawteam/agents` - 获取代理列表
- `POST /api/clawteam/agents` - 创建代理
- `GET /api/clawteam/teams` - 获取团队列表
- `POST /api/clawteam/teams` - 创建团队
- `POST /api/clawteam/teams/{id}/execute` - 执行任务

### Azure DevOps
- `GET /api/ado/configs` - 获取配置列表
- `POST /api/ado/configs` - 创建配置
- `GET /api/ado/workitems` - 获取工作项
- `GET /api/ado/repositories` - 获取代码仓库

### 对话
- `GET /api/conversations` - 获取对话列表
- `POST /api/conversations` - 创建对话
- `POST /api/conversations/{id}/messages` - 发送消息

## 开发计划

### 已实现
- [x] 前端UI和状态管理
- [x] 后端API框架
- [x] 数据库模型和迁移
- [x] Docker Compose配置
- [x] 前端部署

### 待实现
- [ ] 后端Docker镜像构建和部署
- [ ] 向量搜索优化
- [ ] 更多AI模型支持
- [ ] 团队协作功能
- [ ] 移动端适配

## 许可证

MIT License
