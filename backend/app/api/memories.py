"""
记忆API路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.base import get_db
from app.models.memory import Memory
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/memories", tags=["memories"])


# ========== 请求/响应模型 ==========

class MemoryCreate(BaseModel):
    content: str
    memory_type: str = "fact"
    category: Optional[str] = None
    metadata: Optional[dict] = None
    context: Optional[dict] = None


class MemoryExtractRequest(BaseModel):
    text: str


class MemoryResponse(BaseModel):
    id: str
    userId: str
    memoryType: str
    category: Optional[str]
    content: str
    summary: Optional[str]
    importanceScore: float
    confidenceScore: float
    accessCount: int
    metadata: dict
    context: dict
    createdAt: str
    updatedAt: str
    lastAccessed: str
    
    class Config:
        from_attributes = True


class MemorySearchResponse(MemoryResponse):
    similarity: float


# ========== API端点 ==========

@router.get("", response_model=List[MemoryResponse])
async def get_memories(
    memory_type: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """获取记忆列表"""
    service = MemoryService(db)
    memories = await service.get_memories(
        memory_type=memory_type,
        category=category,
        limit=limit,
        offset=offset,
    )
    return [m.to_dict() for m in memories]


@router.post("", response_model=MemoryResponse)
async def create_memory(
    data: MemoryCreate,
    db: Session = Depends(get_db),
):
    """创建记忆"""
    service = MemoryService(db)
    memory = await service.create_memory(
        content=data.content,
        memory_type=data.memory_type,
        category=data.category,
        metadata=data.metadata,
        context=data.context,
    )
    return memory.to_dict()


@router.get("/search", response_model=List[MemorySearchResponse])
async def search_memories(
    query: str,
    top_k: int = Query(5, ge=1, le=20),
    memory_type: Optional[str] = None,
    min_importance: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    """语义搜索记忆"""
    service = MemoryService(db)
    results = await service.search_memories(
        query=query,
        top_k=top_k,
        memory_type=memory_type,
        min_importance=min_importance,
    )
    return results


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: str,
    db: Session = Depends(get_db),
):
    """获取记忆详情"""
    service = MemoryService(db)
    memory = await service.get_memory(memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return memory.to_dict()


@router.delete("/{memory_id}")
async def delete_memory(
    memory_id: str,
    db: Session = Depends(get_db),
):
    """删除记忆"""
    service = MemoryService(db)
    success = await service.delete_memory(memory_id)
    if not success:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return {"message": "记忆已删除"}


@router.post("/extract")
async def extract_memories(
    data: MemoryExtractRequest,
    db: Session = Depends(get_db),
):
    """从文本提取记忆"""
    service = MemoryService(db)
    memories = await service.extract_memories_from_text(data.text)
    return {"memories": [m.to_dict() for m in memories]}
