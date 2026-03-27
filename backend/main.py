from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api import api_router
from config import settings
from db import init_db
from services.memory import MemoryService
from services.watcher import set_scheduler, watcher_engine


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST_DIR = PROJECT_ROOT / "app" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
RESERVED_BACKEND_PREFIXES = ("api", "docs", "redoc", "openapi.json", "health")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")
    scheduler.start()
    set_scheduler(scheduler)
    await watcher_engine.bootstrap()
    watcher_engine.schedule_memory_decay(MemoryService.decay_all)
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="KAM V3 - 个人 AI 控制台。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _is_backend_path(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in RESERVED_BACKEND_PREFIXES)


def _resolve_frontend_asset(full_path: str) -> Path | None:
    candidate = (FRONTEND_DIST_DIR / full_path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


if FRONTEND_INDEX_FILE.exists():

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_root():
        return FileResponse(FRONTEND_INDEX_FILE)


    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_frontend(full_path: str):
        if _is_backend_path(full_path):
            raise HTTPException(status_code=404, detail="Not Found")

        asset = _resolve_frontend_asset(full_path)
        if asset is not None:
            return FileResponse(asset)
        return FileResponse(FRONTEND_INDEX_FILE)

