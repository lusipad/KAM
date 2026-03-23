"""
笔记API路由
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.base import get_db
from app.db.types import IS_POSTGRES
from app.models.note import Note
from app.models.link import Link
from app.services.llm_service import llm_service

router = APIRouter(prefix="/notes", tags=["notes"])


# ========== 请求/响应模型 ==========

class NoteCreate(BaseModel):
    title: str = ""
    content: str = ""
    content_type: str = "markdown"
    path: Optional[str] = None
    metadata: Optional[dict] = None


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[dict] = None


class NoteResponse(BaseModel):
    id: str
    title: str
    content: str
    contentType: str
    path: str
    version: int
    metadata: dict
    stats: dict
    createdAt: str
    updatedAt: str
    
    class Config:
        from_attributes = True


# ========== API端点 ==========

@router.get("", response_model=List[NoteResponse])
async def get_notes(
    search: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """获取笔记列表"""
    query = db.query(Note)
    
    if search:
        query = query.filter(
            Note.title.ilike(f"%{search}%") | 
            Note.content.ilike(f"%{search}%")
        )
    
    if tag:
        query = query.filter(Note.metadata_["tags"].contains([tag]))
    
    notes = query.order_by(Note.updated_at.desc()).offset(offset).limit(limit).all()
    return [note.to_dict() for note in notes]


@router.post("", response_model=NoteResponse)
async def create_note(
    data: NoteCreate,
    db: Session = Depends(get_db),
):
    """创建笔记"""
    path = data.path or f"notes/{datetime.now().strftime('%Y%m%d%H%M%S')}.md"
    word_count = len(data.content.split()) if data.content else 0
    
    note = Note(
        title=data.title,
        content=data.content,
        content_type=data.content_type,
        path=path,
        metadata_=data.metadata or {"tags": [], "aliases": [], "extractedTags": [], "properties": {}},
        stats={
            "wordCount": word_count,
            "linkCount": 0,
            "backlinkCount": 0,
            "viewCount": 0,
            "readingTime": max(1, word_count // 200),
        },
    )
    
    db.add(note)
    db.commit()
    db.refresh(note)
    
    # 异步生成嵌入向量
    try:
        embedding_text = f"{note.title}\n{note.content[:1000]}"
        note.content_vector = await llm_service.create_embedding(embedding_text)
        db.commit()
    except Exception as e:
        print(f"生成嵌入失败: {e}")
    
    return note.to_dict()


@router.get("/{note_id}", response_model=NoteResponse)
async def get_note(
    note_id: str,
    db: Session = Depends(get_db),
):
    """获取笔记详情"""
    from sqlalchemy.dialects.postgresql import UUID
    
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    stats = note.stats or {}
    stats["viewCount"] = stats.get("viewCount", 0) + 1
    note.stats = stats
    db.commit()
    
    return note.to_dict()


@router.put("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: str,
    data: NoteUpdate,
    db: Session = Depends(get_db),
):
    """更新笔记"""
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    if data.title is not None:
        note.title = data.title
    if data.content is not None:
        note.content = data.content
        word_count = len(data.content.split())
        note.stats = {
            **(note.stats or {}),
            "wordCount": word_count,
            "readingTime": max(1, word_count // 200),
        }
    if data.metadata is not None:
        note.metadata_ = {**(note.metadata_ or {}), **data.metadata}
    
    note.version += 1
    db.commit()
    db.refresh(note)
    
    try:
        embedding_text = f"{note.title}\n{note.content[:1000]}"
        note.content_vector = await llm_service.create_embedding(embedding_text)
        db.commit()
    except Exception as e:
        print(f"更新嵌入失败: {e}")
    
    return note.to_dict()


@router.delete("/{note_id}")
async def delete_note(
    note_id: str,
    db: Session = Depends(get_db),
):
    """删除笔记"""
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    db.delete(note)
    db.commit()
    
    return {"message": "笔记已删除"}


@router.get("/{note_id}/links")
async def get_note_links(
    note_id: str,
    db: Session = Depends(get_db),
):
    """获取笔记的链接"""
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    outgoing = [link.to_dict() for link in note.outgoing_links]
    incoming = [link.to_dict() for link in note.incoming_links]
    
    return {
        "outgoing": outgoing,
        "incoming": incoming,
    }


@router.get("/{note_id}/related")
async def get_related_notes(
    note_id: str,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """获取相关笔记（基于向量相似度）"""
    from sqlalchemy import text

    if not IS_POSTGRES:
        return {"notes": []}
    
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    
    if note.content_vector is None:
        return {"notes": []}
    
    result = db.execute(text("""
        SELECT id, title, content,
               1 - (content_vector <=> :query_vector) as similarity
        FROM notes
        WHERE id != :note_id
        ORDER BY content_vector <=> :query_vector
        LIMIT :limit
    """), {
        "query_vector": note.content_vector,
        "note_id": note_id,
        "limit": limit,
    })
    
    related = []
    for row in result:
        related.append({
            "id": str(row.id),
            "title": row.title,
            "content": row.content[:200] + "..." if len(row.content) > 200 else row.content,
            "similarity": row.similarity,
        })
    
    return {"notes": related}
