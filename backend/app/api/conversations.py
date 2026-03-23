"""
对话API路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

from app.db.base import get_db
from app.models.conversation import Conversation, Message
from app.services.llm_service import llm_service
from app.services.memory_service import MemoryService

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ========== 请求/响应模型 ==========

class ConversationCreate(BaseModel):
    title: Optional[str] = "新对话"
    context: Optional[dict] = None


class MessageCreate(BaseModel):
    content: str
    use_memory: Optional[bool] = True


class MessageResponse(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    metadata: dict
    createdAt: str


# ========== API端点 ==========

@router.get("")
async def get_conversations(db: Session = Depends(get_db)):
    """获取所有对话"""
    conversations = db.query(Conversation).order_by(Conversation.updated_at.desc()).all()
    return {"conversations": [c.to_dict() for c in conversations]}


@router.post("")
async def create_conversation(data: ConversationCreate, db: Session = Depends(get_db)):
    """创建对话"""
    conversation = Conversation(
        title=data.title,
        context=data.context or {},
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation.to_dict()


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """获取对话详情"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    return conversation.to_dict()


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str, db: Session = Depends(get_db)):
    """删除对话"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    db.delete(conversation)
    db.commit()
    return {"message": "对话已删除"}


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    data: MessageCreate,
    db: Session = Depends(get_db),
):
    """发送消息"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    # 保存用户消息
    user_message = Message(
        conversation_id=conversation_id,
        role="user",
        content=data.content,
    )
    db.add(user_message)
    
    # 获取历史消息
    history = [
        {"role": m.role, "content": m.content}
        for m in conversation.messages[-10:]  # 最近10条
    ]
    
    # 构建系统提示
    system_prompt = "你是AI工作助手，帮助用户管理知识、记忆和任务。"
    
    # 检索相关记忆
    memories_text = ""
    if data.use_memory:
        memory_service = MemoryService(db)
        memories = await memory_service.search_memories(data.content, top_k=3)
        if memories:
            memories_text = "\n\n相关记忆:\n" + "\n".join([
                f"- {m['content'][:200]}" for m in memories
            ])
            system_prompt += memories_text
    
    # 调用LLM
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": data.content}
    ]
    
    start_time = datetime.utcnow()
    try:
        response = await llm_service.chat_completion(messages)
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # 保存AI回复
        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=response["content"],
            metadata_={
                "model": response.get("model", "unknown"),
                "tokens": response.get("usage", {}).get("total_tokens", 0),
                "latency": latency,
            },
        )
        db.add(assistant_message)
        
        # 更新对话时间
        conversation.updated_at = datetime.utcnow()
        
        # 从AI回复中提取记忆
        if data.use_memory:
            try:
                await memory_service.extract_memories_from_text(response["content"])
            except:
                pass
        
        db.commit()
        db.refresh(assistant_message)
        
        return assistant_message.to_dict()
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"AI响应失败: {str(e)}")


@router.get("/{conversation_id}/messages")
async def get_messages(conversation_id: str, db: Session = Depends(get_db)):
    """获取对话消息"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    return {"messages": [m.to_dict() for m in conversation.messages]}


@router.delete("/{conversation_id}/messages")
async def clear_messages(conversation_id: str, db: Session = Depends(get_db)):
    """清空对话消息"""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="对话不存在")
    
    for message in conversation.messages:
        db.delete(message)
    
    db.commit()
    return {"message": "消息已清空"}
