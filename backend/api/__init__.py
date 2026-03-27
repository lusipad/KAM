from fastapi import APIRouter

from api import home, memory_api, projects, runs, threads, watchers


api_router = APIRouter()
api_router.include_router(projects.router)
api_router.include_router(threads.router)
api_router.include_router(home.router)
api_router.include_router(runs.router)
api_router.include_router(watchers.router)
api_router.include_router(memory_api.router)
