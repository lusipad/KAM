"""
KAM API 路由模块：仅暴露 v2 工作台主链路。
"""
from fastapi import APIRouter

from app.api import memory, projects, runs, skills, threads

api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(threads.router)
api_router.include_router(runs.router)
api_router.include_router(memory.router)
api_router.include_router(skills.router)
