from fastapi import APIRouter, HTTPException


router = APIRouter(tags=["legacy"])


@router.get("/projects", include_in_schema=False)
async def legacy_projects_tombstone():
    raise HTTPException(status_code=404, detail="未找到页面")


@router.get("/threads/{thread_id}", include_in_schema=False)
async def legacy_thread_tombstone(thread_id: str):
    raise HTTPException(status_code=404, detail="未找到页面")


@router.get("/dev/seed-demo", include_in_schema=False)
async def legacy_seed_demo_tombstone():
    raise HTTPException(status_code=404, detail="未找到页面")
