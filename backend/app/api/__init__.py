"""
KAM API 路由模块：保留 Lite Core，并并行挂载 v2 Preview。
"""
from fastapi import APIRouter

from app.api import autonomy, memory, projects, runs, tasks, threads

api_router = APIRouter()
api_router.include_router(tasks.router)
api_router.include_router(autonomy.router)
api_router.include_router(projects.router)
api_router.include_router(threads.router)
api_router.include_router(runs.router)
api_router.include_router(memory.router)
