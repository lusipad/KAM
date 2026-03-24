"""
API路由模块
"""
from fastapi import APIRouter

from app.api import notes, memories, clawteam, ado, conversations, tasks

api_router = APIRouter()

api_router.include_router(notes.router)
api_router.include_router(memories.router)
api_router.include_router(clawteam.router)
api_router.include_router(ado.router)
api_router.include_router(conversations.router)
api_router.include_router(tasks.router)
