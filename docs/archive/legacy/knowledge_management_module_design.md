# AI工作助手 - 知识管理模块技术方案

## 文档信息
- **版本**: v1.0
- **日期**: 2024年
- **状态**: 设计草案
- **目标读者**: 技术团队、架构师

---

## 目录
1. [核心功能设计](#1-核心功能设计)
2. [推荐技术栈](#2-推荐技术栈)
3. [数据模型设计](#3-数据模型设计)
4. [关键实现挑战和解决方案](#4-关键实现挑战和解决方案)
5. [系统接口设计](#5-系统接口设计)
6. [实施路线图](#6-实施路线图)

---

## 1. 核心功能设计

### 1.1 笔记创建和编辑

#### 功能需求
| 功能 | 优先级 | 描述 |
|------|--------|------|
| Markdown编辑器 | P0 | 支持标准Markdown语法，实时预览 |
| 富文本编辑器 | P0 | WYSIWYG编辑，适合非技术用户 |
| 块级编辑 | P1 | Notion风格的块编辑器，支持拖拽重组 |
| 代码高亮 | P1 | 支持100+编程语言的语法高亮 |
| 数学公式 | P2 | LaTeX公式渲染支持 |
| 多媒体嵌入 | P1 | 图片、视频、PDF、音频嵌入 |
| 附件管理 | P1 | 文件上传、版本控制、云端存储 |

#### 编辑器架构设计
```
┌─────────────────────────────────────────────────────────────┐
│                      编辑器架构                              │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Markdown    │  │   Rich Text  │  │   Block      │      │
│  │   Editor     │  │    Editor    │  │   Editor     │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │              │
│         └─────────────────┼─────────────────┘              │
│                           │                                 │
│              ┌────────────┴────────────┐                   │
│              │   Document State Model   │                   │
│              │   (ProseMirror/Yjs)      │                   │
│              └────────────┬────────────┘                   │
│                           │                                 │
│              ┌────────────┴────────────┐                   │
│              │   Content Transformers   │                   │
│              │  (Markdown ↔ JSON ↔ HTML)│                   │
│              └─────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 双链笔记系统

#### 核心概念
双链笔记系统基于**Zettelkasten**方法，实现知识网络化管理。

#### 链接类型
```typescript
interface LinkType {
  // 双向链接 [[Note Title]]
  WIKI_LINK: 'wiki';
  
  // 标签链接 #tag
  TAG_LINK: 'tag';
  
  // 块引用 ^block-id
  BLOCK_REFERENCE: 'block';
  
  // 嵌入引用 ![[Note Title]]
  EMBED_REFERENCE: 'embed';
  
  // 外部链接 [text](url)
  EXTERNAL_LINK: 'external';
}
```

#### 图谱视图功能
| 功能 | 描述 | 技术实现 |
|------|------|----------|
| 全局图谱 | 展示所有笔记的关联关系 | Force-directed graph (D3.js/vis.js) |
| 局部图谱 | 当前笔记的关联网络 | 2-hop neighborhood visualization |
| 路径发现 | 查找两个笔记间的关联路径 | BFS/DFS graph traversal |
| 聚类分析 | 自动识别知识主题群组 | Louvain community detection |
| 时间轴视图 | 按时间展示笔记演进 | Timeline visualization |
| 过滤器 | 按标签/日期/类型筛选 | Dynamic graph filtering |

#### 图谱数据结构
```typescript
interface GraphData {
  nodes: {
    id: string;
    title: string;
    type: 'note' | 'tag' | 'attachment';
    metadata: {
      createdAt: Date;
      updatedAt: Date;
      wordCount: number;
      tags: string[];
    };
    // 可视化属性
    visual: {
      size: number;      // 基于链接数/字数
      color: string;     // 基于标签/聚类
      x?: number;
      y?: number;
    };
  }[];
  
  edges: {
    source: string;
    target: string;
    type: LinkType;
    strength: number;    // 链接强度（共现频率）
  }[];
}
```

### 1.3 AI辅助知识整理

#### AI功能矩阵

| 功能 | 触发时机 | AI模型 | 成本等级 |
|------|----------|--------|----------|
| 自动标签 | 保存时 | GPT-4-mini/Claude-3-Haiku | 低 |
| 智能摘要 | 保存时/手动 | GPT-4/Claude-3-Sonnet | 中 |
| 关联建议 | 编辑时/浏览时 | Embedding + Vector Search | 低 |
| 内容续写 | 用户触发 | GPT-4/Claude-3-Opus | 高 |
| 知识问答 | 用户查询 | RAG + LLM | 中 |
| 重复检测 | 后台任务 | Embedding similarity | 低 |
| 知识图谱增强 | 定期批处理 | Graph Neural Network | 高 |

#### AI处理流程
```
┌─────────────────────────────────────────────────────────────┐
│                    AI辅助处理流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  笔记保存   │───▶│  内容解析   │───▶│  任务分发   │     │
│  └─────────────┘    └─────────────┘    └──────┬──────┘     │
│                                                │            │
│         ┌──────────────────────────────────────┼──────┐     │
│         │                                      │      │     │
│         ▼                                      ▼      ▼     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ Embedding   │    │  标签生成   │    │  摘要生成   │     │
│  │  向量化     │    │  (LLM)      │    │  (LLM)      │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                                      │            │
│         └──────────────────┬───────────────────┘            │
│                            ▼                                │
│                   ┌─────────────────┐                       │
│                   │   结果存储      │                       │
│                   │   (向量DB/图DB) │                       │
│                   └─────────────────┘                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 语义搜索和全文检索

#### 搜索架构
```
┌─────────────────────────────────────────────────────────────┐
│                     混合搜索架构                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   用户查询 ──▶ 查询理解 ──┬──▶ 全文检索 (BM25)              │
│                           │       ↓                         │
│                           │   关键词匹配                    │
│                           │       ↓                         │
│                           ├──▶ 语义检索 (Vector)            │
│                           │       ↓                         │
│                           │   向量相似度                    │
│                           │       ↓                         │
│                           └──▶ 图谱检索 (Graph)             │
│                                   ↓                         │
│                               关系推理                      │
│                                   ↓                         │
│                           ┌──────────────┐                  │
│                           │  结果融合    │                  │
│                           │  (RRF/加权)  │                  │
│                           └──────────────┘                  │
│                                   ↓                         │
│                           ┌──────────────┐                  │
│                           │  重排序(Rerank)│                 │
│                           │  (Cross-Encoder)│                │
│                           └──────────────┘                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 搜索类型

| 搜索类型 | 实现技术 | 适用场景 |
|----------|----------|----------|
| 全文搜索 | Elasticsearch/Meilisearch | 精确关键词匹配 |
| 语义搜索 | Vector DB + Embedding | 概念相似性查找 |
| 模糊搜索 | Fuzzy matching | 拼写容错 |
| 自然语言 | LLM + RAG | 复杂问题回答 |
| 图谱搜索 | Cypher/Gremlin | 关系路径查询 |

### 1.5 知识导入/导出

#### 导入格式支持
| 格式 | 优先级 | 处理方式 |
|------|--------|----------|
| Markdown (.md) | P0 | 原生支持，保留双链语法 |
| Obsidian Vault | P0 | 完整导入，保留链接关系 |
| Notion Export | P1 | HTML/Markdown解析 |
| Evernote (.enex) | P2 | XML解析转换 |
| PDF | P1 | OCR + 文本提取 |
| Web Clipper | P1 | 浏览器插件，智能提取正文 |
| RSS/Atom | P2 | 自动同步订阅源 |

#### 导出格式支持
| 格式 | 描述 |
|------|------|
| Markdown | 标准Markdown，保留双链语法 |
| PDF | 格式化导出，支持样式模板 |
| HTML | 静态网站生成 |
| JSON | 完整数据结构导出 |
| Graph (GEXF/GraphML) | 知识图谱导出 |

---

## 2. 推荐技术栈

### 2.1 前端编辑器技术

#### 编辑器框架对比

| 框架 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **ProseMirror** | 高度可定制、协同编辑原生支持 | 学习曲线陡峭 | 复杂富文本编辑器 |
| **Slate.js** | React友好、API直观 | 性能在大量内容时下降 | React项目 |
| **Tiptap** | 基于ProseMirror、插件丰富 | 灵活性受限 | 快速开发 |
| **Editor.js** | 块编辑器、JSON输出 | 功能相对简单 | 块级编辑需求 |
| **CodeMirror 6** | 代码编辑优秀、轻量 | 富文本支持有限 | Markdown编辑器 |

#### 推荐方案
```
┌────────────────────────────────────────────────────────────┐
│                    前端技术栈推荐                           │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  编辑器核心: ProseMirror + Tiptap                          │
│  ├── Markdown模式: CodeMirror 6                            │
│  ├── 富文本模式: Tiptap + 自定义扩展                       │
│  └── 协同编辑: Yjs + WebRTC/WebSocket                      │
│                                                            │
│  图谱可视化: D3.js / vis-network / react-force-graph       │
│                                                            │
│  UI框架: React + TailwindCSS                               │
│                                                            │
│  状态管理: Zustand / Jotai                                 │
│                                                            │
│  文件处理: PDF.js + Mammoth.js + Turndown                  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### 2.2 后端存储方案

#### 存储分层架构
```
┌─────────────────────────────────────────────────────────────┐
│                      存储分层架构                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 应用层 (Application)                 │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          │                                  │
│  ┌───────────────────────▼─────────────────────────────┐   │
│  │              数据访问层 (Data Access)                │   │
│  │         (ORM: Prisma / TypeORM / Drizzle)            │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          │                                  │
│  ┌─────────────┬─────────┴──────────┬─────────────┐        │
│  │             │                    │             │        │
│  ▼             ▼                    ▼             ▼        │
│ ┌──────┐  ┌────────┐  ┌──────────────┐  ┌────────────┐    │
│ │Relational│ │ Document │  │    Vector      │  │   Graph    │    │
│ │  (PostgreSQL)│ │(MongoDB) │  │  (pgvector/    │  │ (Neo4j/    │    │
│ │           │  │          │  │  Milvus)       │  │  Dgraph)   │    │
│ └──────┘  └────────┘  └──────────────┘  └────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              缓存层 (Redis)                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              对象存储 (S3/MinIO) - 附件              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 数据库选型建议

| 数据类型 | 推荐方案 | 备选方案 | 理由 |
|----------|----------|----------|------|
| 笔记元数据 | PostgreSQL | SQLite | ACID、JSON支持、pgvector |
| 笔记内容 | PostgreSQL (JSONB) | MongoDB | 统一技术栈、事务支持 |
| 向量嵌入 | pgvector | Milvus/Pinecone | 与PG集成、成本可控 |
| 图谱关系 | Neo4j | PostgreSQL + AGE | 复杂图查询、可视化 |
| 全文搜索 | Meilisearch | Elasticsearch | 轻量、易部署 |
| 缓存 | Redis | - | 会话、热点数据 |
| 文件存储 | MinIO/S3 | 本地存储 | 云原生、可扩展 |

### 2.3 向量数据库选择

#### 向量数据库对比

| 特性 | pgvector | Milvus | Pinecone | Chroma | Qdrant |
|------|----------|--------|----------|--------|--------|
| 部署方式 | 自托管 | 自托管/云 | 纯云 | 自托管 | 自托管/云 |
| 成本 | 低 | 中 | 高 | 低 | 中 |
| 性能 | 中 | 高 | 高 | 中 | 高 |
| 扩展性 | 中 | 高 | 高 | 低 | 高 |
| 混合查询 | 优秀 | 好 | 好 | 中 | 好 |
| 学习曲线 | 低 | 中 | 低 | 低 | 中 |

#### 推荐方案
**pgvector** 作为首选方案：
- 与PostgreSQL无缝集成
- 支持混合查询（向量+关系）
- 无需额外运维成本
- 支持HNSW和IVFFlat索引

```sql
-- pgvector 示例配置
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE note_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id UUID REFERENCES notes(id) ON DELETE CASCADE,
    chunk_index INTEGER,
    content TEXT,
    embedding vector(1536),  -- OpenAI embedding dimension
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 创建HNSW索引
CREATE INDEX ON note_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- 相似度搜索查询
SELECT note_id, content, 
       1 - (embedding <=> query_embedding) AS similarity
FROM note_embeddings
WHERE 1 - (embedding <=> query_embedding) > 0.7
ORDER BY embedding <=> query_embedding
LIMIT 10;
```

### 2.4 AI/ML组件

#### Embedding模型选择

| 模型 | 维度 | 语言支持 | 质量 | 成本 | 推荐场景 |
|------|------|----------|------|------|----------|
| OpenAI text-embedding-3-small | 1536 | 多语言 | 高 | 中 | 通用场景 |
| OpenAI text-embedding-3-large | 3072 | 多语言 | 极高 | 高 | 高质量需求 |
| Cohere embed | 1024 | 多语言 | 高 | 中 | 长文本 |
| BGE-M3 (本地) | 1024 | 多语言 | 高 | 低 | 隐私敏感 |
| E5-Mistral (本地) | 4096 | 多语言 | 极高 | 低 | 本地部署 |

#### LLM服务架构
```
┌─────────────────────────────────────────────────────────────┐
│                    LLM服务架构                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                 LLM Router / Gateway                 │   │
│  │         (统一接口、负载均衡、熔断降级)                │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          │                                  │
│         ┌────────────────┼────────────────┐                │
│         │                │                │                │
│         ▼                ▼                ▼                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐           │
│  │  OpenAI    │  │  Anthropic │  │   Local    │           │
│  │  GPT-4     │  │  Claude    │  │   Models   │           │
│  │            │  │            │  │ (Ollama)   │           │
│  └────────────┘  └────────────┘  └────────────┘           │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              缓存层 (语义缓存)                        │   │
│  │         (相似查询结果复用)                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 推荐AI服务栈
| 组件 | 推荐方案 | 用途 |
|------|----------|------|
| Embedding | OpenAI text-embedding-3-small | 文本向量化 |
| LLM (云端) | GPT-4 / Claude-3-Sonnet | 复杂推理任务 |
| LLM (本地) | Ollama + Llama3/Mistral | 隐私敏感场景 |
| 缓存 | GPTCache / 自定义 | 降低API成本 |
| 提示管理 | LangChain / 自定义 | 提示模板管理 |

---

## 3. 数据模型设计

### 3.1 笔记实体模型

```typescript
// 核心笔记实体
interface Note {
  // 主键
  id: UUID;
  
  // 基本属性
  title: string;
  content: string;           // Markdown/JSON格式
  contentType: 'markdown' | 'rich-text' | 'block';
  
  // 层级关系
  parentId?: UUID;           // 文件夹/笔记本
  path: string;              // 文件路径 (e.g., "projects/idea.md")
  
  // 版本控制
  version: number;
  previousVersionId?: UUID;
  
  // 时间戳
  createdAt: DateTime;
  updatedAt: DateTime;
  
  // 元数据
  metadata: NoteMetadata;
  
  // 统计信息
  stats: NoteStats;
}

interface NoteMetadata {
  // 用户定义
  tags: string[];
  aliases: string[];         // 笔记别名，用于双链
  
  // 自动提取
  extractedTags: string[];   // AI提取的标签
  summary?: string;          // AI生成的摘要
  
  // 属性
  properties: Record<string, any>;  // 自定义属性
  
  // 来源信息
  source?: {
    type: 'clip' | 'import' | 'manual';
    url?: string;
    originalPath?: string;
  };
}

interface NoteStats {
  wordCount: number;
  charCount: number;
  readingTime: number;       // 分钟
  linkCount: number;         //  outgoing links
  backlinkCount: number;     // incoming links
  attachmentCount: number;
  viewCount: number;
  lastViewedAt?: DateTime;
}
```

### 3.2 链接关系模型

```typescript
// 链接关系实体 (存储在关系数据库)
interface Link {
  id: UUID;
  
  // 链接端点
  sourceNoteId: UUID;
  targetNoteId: UUID;
  
  // 链接类型
  type: LinkType;
  
  // 链接上下文
  context: {
    sourceText: string;      // 源文本片段
    targetText?: string;     // 目标文本片段
    position: {              // 在源文档中的位置
      start: number;
      end: number;
    };
  };
  
  // 元数据
  isResolved: boolean;       // 目标是否存在
  isEmbed: boolean;          // 是否为嵌入链接
  
  createdAt: DateTime;
  updatedAt: DateTime;
}

// 图谱节点 (存储在图数据库)
interface GraphNode {
  id: string;                // note_id or tag_name
  label: 'note' | 'tag' | 'attachment';
  properties: {
    title: string;
    createdAt: DateTime;
    updatedAt: DateTime;
    wordCount: number;
    // ...其他属性
  };
}

// 图谱边 (存储在图数据库)
interface GraphEdge {
  id: string;
  source: string;            // 源节点ID
  target: string;            // 目标节点ID
  type: 'links_to' | 'tagged_with' | 'references' | 'similar_to';
  properties: {
    weight: number;          // 链接强度
    context?: string;        // 链接上下文
    createdAt: DateTime;
  };
}
```

### 3.3 标签系统模型

```typescript
// 标签实体
interface Tag {
  id: UUID;
  name: string;              // 唯一标识
  displayName: string;       // 显示名称
  color?: string;            // 标签颜色
  icon?: string;             // 标签图标
  
  // 层级关系
  parentId?: UUID;
  path: string;              // 层级路径 (e.g., "tech/ai/ml")
  
  // 描述
  description?: string;
  
  // 统计
  noteCount: number;
  
  // 时间戳
  createdAt: DateTime;
  updatedAt: DateTime;
}

// 笔记-标签关联
interface NoteTag {
  noteId: UUID;
  tagId: UUID;
  confidence?: number;       // AI标签的置信度
  source: 'manual' | 'ai' | 'inherited';
  createdAt: DateTime;
}
```

### 3.4 向量嵌入存储

```typescript
// 文档块 (用于向量化)
interface DocumentChunk {
  id: UUID;
  noteId: UUID;
  
  // 块内容
  content: string;
  chunkIndex: number;        // 在文档中的顺序
  
  // 位置信息
  startPosition: number;     // 在原文中的起始位置
  endPosition: number;
  
  // 上下文
  context: {
    previousChunk?: string;  // 前一块内容（摘要）
    nextChunk?: string;      // 后一块内容（摘要）
    headings: string[];      // 所在章节的标题
  };
  
  // 元数据
  metadata: {
    tokenCount: number;
    charCount: number;
    noteTitle: string;
    notePath: string;
    tags: string[];
  };
}

// 向量嵌入
interface Embedding {
  id: UUID;
  chunkId: UUID;
  noteId: UUID;
  
  // 向量数据
  vector: number[];          // 1536维 (OpenAI)
  model: string;             // 使用的模型
  modelVersion: string;
  
  // 时间戳
  createdAt: DateTime;
}

// 语义搜索缓存
interface SemanticSearchCache {
  id: UUID;
  query: string;
  queryEmbedding: number[];
  
  // 缓存结果
  results: {
    chunkId: UUID;
    similarity: number;
  }[];
  
  // 元数据
  hitCount: number;
  lastAccessedAt: DateTime;
  expiresAt: DateTime;
  
  createdAt: DateTime;
}
```

### 3.5 数据库Schema (PostgreSQL)

```sql
-- 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- 笔记表
CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    content_type VARCHAR(20) NOT NULL DEFAULT 'markdown',
    parent_id UUID REFERENCES notes(id) ON DELETE SET NULL,
    path TEXT NOT NULL UNIQUE,
    version INTEGER NOT NULL DEFAULT 1,
    previous_version_id UUID,
    
    -- 元数据 (JSONB)
    metadata JSONB NOT NULL DEFAULT '{}',
    
    -- 统计
    word_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    reading_time INTEGER NOT NULL DEFAULT 0,
    link_count INTEGER NOT NULL DEFAULT 0,
    backlink_count INTEGER NOT NULL DEFAULT 0,
    
    -- 时间戳
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- 全文搜索向量
    search_vector tsvector
);

-- 链接表
CREATE TABLE links (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    target_note_id UUID REFERENCES notes(id) ON DELETE SET NULL,
    link_type VARCHAR(50) NOT NULL,
    
    -- 上下文
    source_text TEXT,
    position_start INTEGER,
    position_end INTEGER,
    
    -- 状态
    is_resolved BOOLEAN NOT NULL DEFAULT false,
    is_embed BOOLEAN NOT NULL DEFAULT false,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(source_note_id, target_note_id, position_start)
);

-- 标签表
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    color VARCHAR(7),
    icon VARCHAR(50),
    parent_id UUID REFERENCES tags(id) ON DELETE SET NULL,
    path TEXT NOT NULL,
    description TEXT,
    note_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 笔记-标签关联表
CREATE TABLE note_tags (
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    confidence FLOAT,
    source VARCHAR(20) NOT NULL DEFAULT 'manual',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (note_id, tag_id)
);

-- 向量嵌入表
CREATE TABLE embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    token_count INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(note_id, chunk_index)
);

-- 索引
CREATE INDEX idx_notes_parent ON notes(parent_id);
CREATE INDEX idx_notes_updated ON notes(updated_at DESC);
CREATE INDEX idx_notes_search ON notes USING GIN(search_vector);

CREATE INDEX idx_links_source ON links(source_note_id);
CREATE INDEX idx_links_target ON links(target_note_id);
CREATE INDEX idx_links_type ON links(link_type);

CREATE INDEX idx_tags_parent ON tags(parent_id);
CREATE INDEX idx_tags_path ON tags(path);

CREATE INDEX idx_embeddings_note ON embeddings(note_id);
CREATE INDEX idx_embeddings_vector ON embeddings 
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- 全文搜索更新触发器
CREATE OR REPLACE FUNCTION update_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('simple', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('simple', COALESCE(NEW.content, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_search_vector
    BEFORE INSERT OR UPDATE ON notes
    FOR EACH ROW
    EXECUTE FUNCTION update_search_vector();
```

---

## 4. 关键实现挑战和解决方案

### 4.1 大规模笔记的性能优化

#### 挑战分析
- 10万+笔记的加载和渲染
- 大规模图谱的流畅交互
- 全文搜索的响应时间
- 向量搜索的高维计算

#### 解决方案

```
┌─────────────────────────────────────────────────────────────┐
│                  性能优化策略                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 数据分页与虚拟滚动                                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - 笔记列表: 虚拟滚动 (react-window)                │   │
│  │  - 图谱渲染: 视口裁剪 + LOD (Level of Detail)       │   │
│  │  - 搜索结果: 无限滚动加载                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  2. 索引优化                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - 全文搜索: GIN索引 + tsvector                     │   │
│  │  - 向量搜索: HNSW索引 (ef_search调优)               │   │
│  │  - 图谱查询: 节点/边属性索引                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  3. 缓存策略                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - 笔记内容: LRU缓存 (最近访问)                     │   │
│  │  - 搜索结果: 语义缓存 (相似查询复用)                │   │
│  │  - 图谱数据: 增量更新 + 本地缓存                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  4. 后台处理                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - 链接解析: 异步任务队列 (Bull/BullMQ)             │   │
│  │  - AI处理: 批处理 + 优先级队列                      │   │
│  │  - 索引更新: 增量更新 + 批量重建                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 性能指标目标
| 场景 | 目标响应时间 | 优化策略 |
|------|--------------|----------|
| 笔记列表加载 | < 100ms | 分页 + 虚拟滚动 |
| 全文搜索 | < 200ms | GIN索引 + 缓存 |
| 语义搜索 | < 500ms | HNSW索引 + 预计算 |
| 图谱渲染(1k节点) | < 1s | WebGL + 视口裁剪 |
| 图谱渲染(10k节点) | < 3s | 聚合 + LOD |

### 4.2 实时协作同步

#### 架构设计
```
┌─────────────────────────────────────────────────────────────┐
│                  实时协作架构                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   客户端A          协作服务器           客户端B             │
│  ┌─────┐          ┌─────────┐          ┌─────┐             │
│  │ Yjs │◀────────▶│  Yjs    │◀────────▶│ Yjs │             │
│  │ Doc │  WebSocket│  Server │  WebSocket│ Doc │             │
│  └──┬──┘          └────┬────┘          └──┬──┘             │
│     │                  │                   │                │
│     ▼                  ▼                   ▼                │
│  ┌─────┐          ┌─────────┐          ┌─────┐             │
│  │Prose│          │  Redis  │          │Prose│             │
│  │Mirror│         │ (PubSub)│          │Mirror│            │
│  └─────┘          └─────────┘          └─────┘             │
│                                                             │
│  冲突解决: Yjs CRDT (Conflict-free Replicated Data Type)   │
│  持久化: 定期快照 + 操作日志                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 实现要点
| 方面 | 方案 | 说明 |
|------|------|------|
| 冲突解决 | Yjs CRDT | 自动合并，无需锁机制 |
| 状态同步 | WebSocket | 低延迟双向通信 |
| 离线支持 | 本地优先 | 离线编辑，在线同步 |
| 权限控制 | 操作级权限 | 读/写/评论权限分离 |
| 版本历史 | 操作日志 | 完整编辑历史回溯 |

### 4.3 AI处理成本控制

#### 成本优化策略
```
┌─────────────────────────────────────────────────────────────┐
│                  AI成本控制策略                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 分层处理策略                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  简单任务: 本地模型 (Ollama/Llama3)                 │   │
│  │  标准任务: 轻量模型 (GPT-4-mini/Claude-Haiku)       │   │
│  │  复杂任务: 强力模型 (GPT-4/Claude-Opus)             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  2. 缓存与复用                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - 语义缓存: 相似查询直接返回缓存结果               │   │
│  │  - 增量更新: 仅处理变更内容                         │   │
│  │  - 批处理: 合并多个小任务一次性处理                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  3. 智能触发                                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - 防抖处理: 编辑停止后延迟触发                     │   │
│  │  - 用户确认: 高成本操作需用户确认                   │   │
│  │  - 后台处理: 低优先级任务非高峰执行                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  4. 成本控制规则                                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  - 每日限额: 用户/全局每日Token上限                 │   │
│  │  - 优先级队列: 高优先级任务优先处理                 │   │
│  │  - 降级策略: 超额时切换至本地模型                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 成本估算模型
```typescript
interface AICostConfig {
  // 每日限额
  dailyTokenLimit: number;
  
  // 模型选择阈值
  modelSelection: {
    embedding: {
      default: 'text-embedding-3-small';
      highQuality: 'text-embedding-3-large';
    };
    completion: {
      simple: 'gpt-4o-mini';
      standard: 'gpt-4o';
      complex: 'gpt-4-turbo';
    };
  };
  
  // 触发条件
  triggers: {
    autoTag: 'on_save' | 'manual' | 'scheduled';
    autoSummary: 'on_save' | 'manual';
    linkSuggestion: 'on_edit' | 'on_view';
  };
  
  // 缓存配置
  cache: {
    semanticCacheEnabled: boolean;
    cacheTTL: number;        // 秒
    similarityThreshold: number;
  };
}
```

### 4.4 本地优先与云同步平衡

#### 架构设计
```
┌─────────────────────────────────────────────────────────────┐
│               本地优先 + 云同步架构                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    客户端                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │   SQLite    │  │  Vector DB  │  │   File      │ │   │
│  │  │  (主存储)    │  │  (本地向量)  │  │  (附件)     │ │   │
│  │  └──────┬──────┘  └─────────────┘  └─────────────┘ │   │
│  │         │                                          │   │
│  │  ┌──────▼──────────────────────────────────────┐  │   │
│  │  │           Sync Engine (本地优先)             │  │   │
│  │  │  - CRDT状态管理                              │  │   │
│  │  │  - 离线队列                                  │  │   │
│  │  │  - 冲突解决                                  │  │   │
│  │  └──────┬──────────────────────────────────────┘  │   │
│  └─────────┼─────────────────────────────────────────┘   │
│            │                                               │
│            │ WebSocket / HTTPS                             │
│            ▼                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    云端服务                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │ PostgreSQL  │  │   Milvus    │  │    S3       │ │   │
│  │  │  (主存储)    │  │  (向量搜索)  │  │  (对象存储)  │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘ │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  同步策略:                                                  │
│  - 元数据: 实时同步                                         │
│  - 内容: 增量同步 (基于操作日志)                             │
│  - 向量: 云端计算，本地缓存                                  │
│  - 附件: 按需同步 + 后台预取                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 同步策略
| 数据类型 | 本地存储 | 云端存储 | 同步策略 |
|----------|----------|----------|----------|
| 笔记元数据 | SQLite | PostgreSQL | 实时同步 |
| 笔记内容 | SQLite | PostgreSQL | 增量同步 |
| 向量嵌入 | 可选 | pgvector | 云端计算，本地缓存 |
| 全文索引 | 可选 | Meilisearch | 云端处理 |
| 附件 | 本地文件 | S3/MinIO | 按需同步 |
| 图谱数据 | 本地计算 | Neo4j | 云端为主 |

---

## 5. 系统接口设计

### 5.1 与长期记忆系统的交互

#### 接口架构
```
┌─────────────────────────────────────────────────────────────┐
│              知识管理 ↔ 长期记忆 交互架构                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐          ┌──────────────────┐        │
│  │   知识管理模块    │◀────────▶│   长期记忆系统    │        │
│  │                  │   API    │                  │        │
│  │  - 笔记存储      │          │  - 对话历史      │        │
│  │  - 知识图谱      │          │  - 用户偏好      │        │
│  │  - 语义搜索      │          │  - 上下文记忆    │        │
│  │  - AI处理        │          │  - 事实记忆      │        │
│  └──────────────────┘          └──────────────────┘        │
│                                                             │
│  交互模式:                                                  │
│  1. 知识注入: 笔记内容 → 记忆上下文                         │
│  2. 记忆提取: 对话历史 → 知识关联                           │
│  3. 双向增强: 知识图谱 ↔ 记忆图谱                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### API接口定义
```typescript
// 知识管理 → 长期记忆
interface KnowledgeToMemoryAPI {
  // 获取相关笔记作为上下文
  getRelevantNotes(query: string, options: {
    limit?: number;
    minSimilarity?: number;
    includeMetadata?: boolean;
  }): Promise<RelevantNote[]>;
  
  // 获取笔记摘要
  getNoteSummary(noteId: string): Promise<string>;
  
  // 获取知识图谱路径
  getKnowledgePath(fromNoteId: string, toNoteId: string): Promise<NotePath>;
  
  // 订阅笔记变更
  subscribeToNoteChanges(noteId: string, callback: (change: NoteChange) => void): void;
}

// 长期记忆 → 知识管理
interface MemoryToKnowledgeAPI {
  // 保存重要对话到笔记
  saveConversationToNote(conversation: Conversation, options: {
    notebook?: string;
    autoTag?: boolean;
  }): Promise<Note>;
  
  // 基于记忆推荐相关笔记
  recommendNotesFromMemory(memoryContext: MemoryContext): Promise<NoteRecommendation[]>;
  
  // 同步用户偏好到知识标签
  syncUserPreferencesToTags(preferences: UserPreferences): Promise<void>;
}
```

### 5.2 为ClawTeam提供知识支持

#### 集成架构
```
┌─────────────────────────────────────────────────────────────┐
│              知识管理 → ClawTeam 支持架构                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   知识管理模块                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │  笔记库      │  │  知识图谱    │  │  语义搜索    │ │   │
│  │  │  (Source)   │  │  (Graph)    │  │  (Search)   │ │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │   │
│  │         │                │                │        │   │
│  │         └────────────────┼────────────────┘        │   │
│  │                          │                         │   │
│  │              ┌───────────▼───────────┐             │   │
│  │              │   Knowledge Service   │             │   │
│  │              │   (统一知识接口)       │             │   │
│  │              └───────────┬───────────┘             │   │
│  └──────────────────────────┼─────────────────────────┘   │
│                             │                              │
│                             │ gRPC / REST                  │
│                             ▼                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    ClawTeam                         │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │  任务规划    │  │  代码生成    │  │  问题诊断    │ │   │
│  │  │  (Planner)  │  │  (Coder)    │  │  (Debugger) │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘ │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 知识服务API
```typescript
// 统一知识服务接口
interface KnowledgeService {
  // 代码知识查询
  queryCodeKnowledge(query: CodeQuery): Promise<CodeKnowledgeResult>;
  
  // 架构知识查询
  queryArchitectureKnowledge(query: string): Promise<ArchitectureKnowledge>;
  
  // 最佳实践查询
  queryBestPractices(context: PracticeContext): Promise<BestPractice[]>;
  
  // 项目文档检索
  queryProjectDocs(projectId: string, query: string): Promise<DocResult[]>;
  
  // 技术栈知识
  getTechStackKnowledge(techStack: string[]): Promise<TechStackKnowledge>;
  
  // 实时知识推送
  subscribeToKnowledgeUpdates(subscription: KnowledgeSubscription): void;
}

// 代码知识查询
interface CodeQuery {
  query: string;
  language?: string;
  framework?: string;
  context?: {
    currentFile?: string;
    projectStructure?: string;
  };
}

interface CodeKnowledgeResult {
  snippets: CodeSnippet[];
  explanations: string[];
  relatedDocs: DocumentReference[];
  confidence: number;
}
```

#### 知识注入场景
| 场景 | 知识来源 | 使用方式 |
|------|----------|----------|
| 代码生成 | 技术文档、代码示例 | RAG增强提示 |
| Bug修复 | 问题解决方案库 | 相似问题匹配 |
| 架构设计 | 设计文档、决策记录 | 约束条件注入 |
| 代码审查 | 编码规范、最佳实践 | 规则验证 |
| 技术选型 | 技术评估文档 | 决策支持 |

---

## 6. 实施路线图

### 阶段划分

```
┌─────────────────────────────────────────────────────────────┐
│                    实施路线图                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 1: 基础功能 (MVP) - 6周                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ✓ Markdown编辑器                                    │   │
│  │  ✓ 基础笔记CRUD                                      │   │
│  │  ✓ 文件系统存储                                      │   │
│  │  ✓ 基础全文搜索                                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Phase 2: 双链系统 - 4周                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ✓ Wiki链接解析                                      │   │
│  │  ✓ 反向链接追踪                                      │   │
│  │  ✓ 基础图谱视图                                      │   │
│  │  ✓ 标签系统                                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Phase 3: AI增强 - 6周                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ✓ 向量嵌入存储                                      │   │
│  │  ✓ 语义搜索                                          │   │
│  │  ✓ 自动标签/摘要                                     │   │
│  │  ✓ 关联建议                                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Phase 4: 高级功能 - 6周                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ✓ 实时协作                                          │   │
│  │  ✓ 富文本编辑器                                      │   │
│  │  ✓ 高级图谱分析                                      │   │
│  │  ✓ 知识问答 (RAG)                                    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Phase 5: 系统集成 - 4周                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ✓ 长期记忆集成                                      │   │
│  │  ✓ ClawTeam知识支持                                  │   │
│  │  ✓ 导入/导出完善                                     │   │
│  │  ✓ 性能优化                                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 技术债务管理
| 阶段 | 技术债务 | 处理策略 |
|------|----------|----------|
| Phase 1 | SQLite单文件限制 | Phase 3迁移至PostgreSQL |
| Phase 2 | 简单图谱渲染 | Phase 4升级至WebGL |
| Phase 3 | 同步向量计算 | Phase 4引入异步队列 |
| Phase 4 | 基础缓存 | Phase 5引入多级缓存 |

---

## 附录

### A. 参考资源
- [ProseMirror Documentation](https://proseMirror.net/docs/)
- [Yjs - Shared Editing](https://docs.yjs.dev/)
- [pgvector](https://github.com/pgvector/pgvector)
- [Obsidian Publish API](https://publish.obsidian.md/help/)

### B. 术语表
| 术语 | 说明 |
|------|------|
| CRDT | Conflict-free Replicated Data Type，无冲突复制数据类型 |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| HNSW | Hierarchical Navigable Small World，分层可导航小世界图 |
| BM25 | Best Match 25，经典全文检索评分算法 |

---

*文档结束*
