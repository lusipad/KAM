from fastapi import APIRouter

from api import context_snapshots, dev, legacy, reviews, runs, tasks
from config import settings


api_router = APIRouter()
api_router.include_router(tasks.router)
api_router.include_router(context_snapshots.router)
api_router.include_router(reviews.router)
api_router.include_router(runs.router)
api_router.include_router(legacy.router)
if settings.app_env != "production":
    api_router.include_router(dev.router)
