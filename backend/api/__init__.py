from fastapi import APIRouter

from api import context_snapshots, dev, home, memory_api, projects, reviews, runs, tasks, threads, watchers
from config import settings


api_router = APIRouter()
api_router.include_router(tasks.router)
api_router.include_router(context_snapshots.router)
api_router.include_router(reviews.router)
api_router.include_router(runs.router)
if settings.enable_legacy_v3:
    api_router.include_router(projects.router)
    api_router.include_router(threads.router)
    api_router.include_router(home.router)
    api_router.include_router(watchers.router)
    api_router.include_router(memory_api.router)
if settings.app_env != "production":
    api_router.include_router(dev.router)
