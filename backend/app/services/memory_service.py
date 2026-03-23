"""
记忆服务 - 长期记忆管理
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.db.types import IS_POSTGRES, IS_SQLITE
from app.services.llm_service import llm_service


class MemoryService:
    """记忆服务类"""
    
    def __init__(self, db: Session):
        self.db = db
    
    async def create_memory(
        self,
        content: str,
        memory_type: str = "fact",
        category: Optional[str] = None,
        user_id: str = "default",
        metadata: Optional[Dict] = None,
        context: Optional[Dict] = None,
    ) -> Memory:
        """
        创建新记忆
        
        Args:
            content: 记忆内容
            memory_type: 记忆类型 (fact, procedure, episodic)
            category: 分类
            user_id: 用户ID
            metadata: 元数据
            context: 上下文
        
        Returns:
            创建的记忆对象
        """
        content_vector = None
        summary = content[:100] if len(content) > 100 else content
        summary_vector = None
        importance_score = 0.5

        try:
            content_vector = await llm_service.create_embedding(content)
            summary = await self._generate_summary(content)
            summary_vector = await llm_service.create_embedding(summary) if summary else None
            importance_score = await self._calculate_importance(content)
        except Exception as e:
            print(f"记忆增强信息生成失败，已降级为基础存储: {e}")
        
        memory = Memory(
            user_id=user_id,
            memory_type=memory_type,
            category=category,
            content=content,
            content_vector=content_vector,
            summary=summary,
            summary_vector=summary_vector,
            importance_score=importance_score,
            metadata_=metadata or {},
            context=context or {},
        )
        
        self.db.add(memory)
        self.db.commit()
        self.db.refresh(memory)
        
        return memory
    
    async def search_memories(
        self,
        query: str,
        user_id: str = "default",
        top_k: int = 5,
        memory_type: Optional[str] = None,
        min_importance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """
        语义搜索记忆
        
        Args:
            query: 查询文本
            user_id: 用户ID
            top_k: 返回结果数量
            memory_type: 记忆类型筛选
            min_importance: 最小重要性分数
        
        Returns:
            记忆列表（包含相似度分数）
        """
        if not IS_POSTGRES:
            return self._search_memories_fallback(
                query=query,
                user_id=user_id,
                top_k=top_k,
                memory_type=memory_type,
                min_importance=min_importance,
            )

        # 生成查询向量
        query_vector = await llm_service.create_embedding(query)
        
        # 构建SQL查询
        sql = """
            SELECT 
                id, user_id, memory_type, category, content, summary,
                importance_score, confidence_score, access_count, metadata, context,
                created_at, updated_at, last_accessed,
                1 - (content_vector <=> :query_vector) as similarity
            FROM memories
            WHERE user_id = :user_id
            AND importance_score >= :min_importance
        """
        
        params = {
            "query_vector": query_vector,
            "user_id": user_id,
            "min_importance": min_importance,
        }
        
        if memory_type:
            sql += " AND memory_type = :memory_type"
            params["memory_type"] = memory_type
        
        sql += " ORDER BY content_vector <=> :query_vector LIMIT :top_k"
        params["top_k"] = top_k
        
        result = self.db.execute(text(sql), params)
        
        memories = []
        for row in result:
            memory = {
                "id": str(row.id),
                "userId": row.user_id,
                "memoryType": row.memory_type,
                "category": row.category,
                "content": row.content,
                "summary": row.summary,
                "importanceScore": row.importance_score,
                "confidenceScore": row.confidence_score,
                "accessCount": row.access_count,
                "metadata": row.metadata,
                "context": row.context,
                "createdAt": row.created_at.isoformat() if row.created_at else None,
                "updatedAt": row.updated_at.isoformat() if row.updated_at else None,
                "lastAccessed": row.last_accessed.isoformat() if row.last_accessed else None,
                "similarity": row.similarity,
            }
            memories.append(memory)
            
            # 更新访问计数
            self._update_access_count(row.id)
        
        return memories
    
    async def get_memories(
        self,
        user_id: str = "default",
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Memory]:
        """获取记忆列表"""
        query = self.db.query(Memory).filter(Memory.user_id == user_id)
        
        if memory_type:
            query = query.filter(Memory.memory_type == memory_type)
        if category:
            query = query.filter(Memory.category == category)
        
        return query.order_by(Memory.updated_at.desc()).offset(offset).limit(limit).all()
    
    async def get_memory(self, memory_id: str) -> Optional[Memory]:
        """获取单个记忆"""
        memory = self.db.query(Memory).filter(Memory.id == memory_id).first()
        if memory:
            memory.access_count += 1
            memory.last_accessed = datetime.utcnow()
            self.db.commit()
        return memory
    
    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        memory = self.db.query(Memory).filter(Memory.id == memory_id).first()
        if memory:
            self.db.delete(memory)
            self.db.commit()
            return True
        return False
    
    async def extract_memories_from_text(
        self,
        text: str,
        user_id: str = "default",
    ) -> List[Memory]:
        """
        从文本中提取记忆
        
        Args:
            text: 输入文本
            user_id: 用户ID
        
        Returns:
            提取的记忆列表
        """
        # 使用LLM提取关键信息
        prompt = f"""从以下文本中提取关键信息作为记忆。请识别：
1. 事实性信息（如用户的偏好、背景信息）
2. 程序性信息（如工作流程、方法）
3. 情境性信息（如重要事件、对话内容）

对于每条记忆，请输出：
- 类型: fact/procedure/episodic
- 内容: 记忆的详细内容
- 分类: 适当的分类标签

文本：
{text}

请以JSON格式输出记忆列表：
{{"memories": [{{"type": "...", "content": "...", "category": "..."}}]}}"""

        try:
            response = await llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            
            import json
            result = json.loads(response["content"])
            memories_data = result.get("memories", [])
            
            created_memories = []
            for mem_data in memories_data:
                memory = await self.create_memory(
                    content=mem_data["content"],
                    memory_type=mem_data.get("type", "fact"),
                    category=mem_data.get("category"),
                    user_id=user_id,
                    context={"source": "extracted", "original_text": text[:500]},
                )
                created_memories.append(memory)
            
            return created_memories
        except Exception as e:
            print(f"记忆提取失败: {e}")
            return []
    
    async def _generate_summary(self, content: str) -> str:
        """生成内容摘要"""
        if len(content) < 100:
            return content
        
        prompt = f"""请将以下内容总结为一句话（不超过50字）：

{content[:1000]}"""
        
        try:
            response = await llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=100,
            )
            return response["content"].strip()
        except:
            return content[:100]
    
    async def _calculate_importance(self, content: str) -> float:
        """计算内容重要性分数"""
        prompt = f"""请评估以下内容的重要性（0-1之间，保留两位小数）：

{content[:500]}

只输出数字，不要其他内容。"""
        
        try:
            response = await llm_service.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=10,
            )
            score = float(response["content"].strip())
            return max(0.0, min(1.0, score))
        except:
            return 0.5
    
    def _update_access_count(self, memory_id: str):
        """更新访问计数"""
        self.db.execute(
            text("UPDATE memories SET access_count = access_count + 1, last_accessed = NOW() WHERE id = :id"),
            {"id": memory_id}
        )
        self.db.commit()

    def _search_memories_fallback(
        self,
        query: str,
        user_id: str,
        top_k: int,
        memory_type: Optional[str],
        min_importance: float,
    ) -> List[Dict[str, Any]]:
        """
        SQLite 本地开发环境使用简单文本匹配兜底搜索。
        """
        db_query = self.db.query(Memory).filter(
            Memory.user_id == user_id,
            Memory.importance_score >= min_importance,
        )

        if memory_type:
            db_query = db_query.filter(Memory.memory_type == memory_type)

        if query:
            pattern = f"%{query}%"
            db_query = db_query.filter(
                or_(
                    Memory.content.ilike(pattern),
                    Memory.summary.ilike(pattern),
                    Memory.category.ilike(pattern),
                )
            )

        items = db_query.order_by(Memory.updated_at.desc()).limit(top_k).all()
        results = []
        for item in items:
            data = item.to_dict()
            data["similarity"] = 1.0 if query and query in (item.content or "") else 0.0
            results.append(data)
            item.access_count += 1
            item.last_accessed = datetime.utcnow()

        self.db.commit()
        return results
