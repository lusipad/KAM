"""
Azure DevOps API路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.base import get_db
from app.services.ado_service import ADOService

router = APIRouter(prefix="/ado", tags=["ado"])


# ========== 请求/响应模型 ==========

class ConfigCreate(BaseModel):
    name: str
    server_url: str
    collection: Optional[str] = "DefaultCollection"
    project: str
    auth_type: Optional[str] = "pat"
    credentials: Optional[dict] = None
    scopes: Optional[List[str]] = None


class ConfigUpdate(BaseModel):
    name: Optional[str] = None
    server_url: Optional[str] = None
    collection: Optional[str] = None
    project: Optional[str] = None
    auth_type: Optional[str] = None
    credentials: Optional[dict] = None
    scopes: Optional[List[str]] = None


# ========== 配置API ==========

@router.get("/configs")
async def get_configs(db: Session = Depends(get_db)):
    """获取所有配置"""
    service = ADOService(db)
    configs = service.get_configs()
    return {"configs": [c.to_dict() for c in configs]}


@router.post("/configs")
async def create_config(data: ConfigCreate, db: Session = Depends(get_db)):
    """创建配置"""
    service = ADOService(db)
    config = service.create_config(data.dict())
    return config.to_dict()


@router.get("/configs/{config_id}")
async def get_config(config_id: str, db: Session = Depends(get_db)):
    """获取配置详情"""
    service = ADOService(db)
    config = service.get_config(config_id)
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    return config.to_dict()


@router.put("/configs/{config_id}")
async def update_config(config_id: str, data: ConfigUpdate, db: Session = Depends(get_db)):
    """更新配置"""
    service = ADOService(db)
    config = service.update_config(config_id, data.dict(exclude_unset=True))
    if not config:
        raise HTTPException(status_code=404, detail="配置不存在")
    return config.to_dict()


@router.delete("/configs/{config_id}")
async def delete_config(config_id: str, db: Session = Depends(get_db)):
    """删除配置"""
    service = ADOService(db)
    success = service.delete_config(config_id)
    if not success:
        raise HTTPException(status_code=404, detail="配置不存在")
    return {"message": "配置已删除"}


@router.post("/configs/{config_id}/test")
async def test_config(config_id: str, db: Session = Depends(get_db)):
    """测试连接"""
    service = ADOService(db)
    result = await service.test_connection(config_id)
    return result


# ========== 工作项API ==========

@router.get("/configs/{config_id}/workitems")
async def get_workitems(
    config_id: str,
    query: Optional[str] = None,
    top: int = 50,
    db: Session = Depends(get_db),
):
    """获取工作项"""
    service = ADOService(db)
    try:
        workitems = await service.get_work_items(config_id, query, top)
        return {"workItems": workitems}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 仓库API ==========

@router.get("/configs/{config_id}/repositories")
async def get_repositories(config_id: str, db: Session = Depends(get_db)):
    """获取代码仓库"""
    service = ADOService(db)
    try:
        repos = await service.get_repositories(config_id)
        return {"repositories": repos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== 构建API ==========

@router.get("/configs/{config_id}/builds")
async def get_builds(
    config_id: str,
    top: int = 20,
    db: Session = Depends(get_db),
):
    """获取构建列表"""
    service = ADOService(db)
    try:
        builds = await service.get_builds(config_id, top)
        return {"builds": builds}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
