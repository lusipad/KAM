"""
Lite Core API 路由模块
"""
from fastapi import APIRouter

from app.api import autonomy, tasks

api_router = APIRouter()
api_router.include_router(tasks.router)
api_router.include_router(autonomy.router)
