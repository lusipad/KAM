# AI工作助手

一个功能完整的AI工作助手软件，集成了知识管理、长期记忆、自定义AI代理团队和Azure DevOps项目同步功能。

## 已部署的前端

**在线访问**: https://fqylk3g4ykmtk.ok.kimi.link

## 功能特性

### 1. 知识管理（类似Obsidian）
- 双链笔记系统，支持笔记间的双向链接
- 富文本编辑器，支持Markdown
- 知识图谱可视化
- 标签管理和全文搜索
- 自动保存和版本历史

### 2. 长期记忆系统
- 基于向量数据库的记忆存储
- 语义搜索和相似度检索
- 记忆类型分类（事实、程序、情境）
- 重要性评分和访问统计
- RAG（检索增强生成）支持

### 3. ClawTeam - 自定义AI代理团队
- 8种代理角色：规划者、分解者、路由者、执行者、专家、验证者、批评者、综合者
- 4种团队拓扑：层级式、对等式、黑板式、管道式
- 任务分解和并行执行
- 实时任务状态跟踪

### 4. Azure DevOps Server集成
- 工作项同步和管理
- 代码仓库浏览
- 构建发布跟踪
- 支持PAT和OAuth认证

### 5. AI对话
- 支持GPT-4等大语言模型
- 上下文感知的智能回复
- 集成知识库和记忆检索
- 对话历史管理

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
- OpenAI API集成

### 数据库
- PostgreSQL 15 + pgvector扩展（向量存储）
- Redis（缓存和消息队列）

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
cd /mnt/okcomputer/output
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
