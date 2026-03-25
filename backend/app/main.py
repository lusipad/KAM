"""
KAM - FastAPI 主应用
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api import api_router
from app.core.config import settings
from app.db.base import init_db


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = PROJECT_ROOT / "app" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
RESERVED_BACKEND_PREFIXES = ("api", "docs", "redoc", "openapi.json", "health")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="KAM - 个人 AI 指挥台，围绕 Project / Thread / Run / Memory 组织持续工作。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app_cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


def _is_backend_path(path: str) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in RESERVED_BACKEND_PREFIXES)


def _resolve_frontend_file(full_path: str) -> Path | None:
    candidate = (FRONTEND_DIST_DIR / full_path).resolve()
    try:
        candidate.relative_to(FRONTEND_DIST_DIR.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


if FRONTEND_INDEX_FILE.exists():
    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_frontend_root():
        return FileResponse(FRONTEND_INDEX_FILE)


    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_frontend_app(full_path: str):
        if _is_backend_path(full_path):
            raise HTTPException(status_code=404, detail="Not Found")

        asset_file = _resolve_frontend_file(full_path)
        if asset_file is not None:
            return FileResponse(asset_file)

        return FileResponse(FRONTEND_INDEX_FILE)
else:
    @app.get("/")
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
            "docs": "/docs",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
