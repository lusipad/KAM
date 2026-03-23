"""
ClawTeam API路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.base import get_db
from app.services.clawteam_service import ClawTeamService

router = APIRouter(prefix="/clawteam", tags=["clawteam"])


# ========== 请求/响应模型 ==========

class AgentCreate(BaseModel):
    name: str
    role: str
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = "gpt-4"
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2000
    tools: Optional[List[str]] = None


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    tools: Optional[List[str]] = None


class TeamCreate(BaseModel):
    name: str
    description: Optional[str] = None
    topology: Optional[str] = "hierarchical"
    coordinator_id: Optional[str] = None
    agent_ids: Optional[List[str]] = None


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    topology: Optional[str] = None
    coordinator_id: Optional[str] = None
    agent_ids: Optional[List[str]] = None


class TaskExecute(BaseModel):
    description: str


# ========== 代理API ==========

@router.get("/agents")
async def get_agents(db: Session = Depends(get_db)):
    """获取所有代理"""
    service = ClawTeamService(db)
    agents = service.get_agents()
    return {"agents": [a.to_dict() for a in agents]}


@router.post("/agents")
async def create_agent(data: AgentCreate, db: Session = Depends(get_db)):
    """创建代理"""
    service = ClawTeamService(db)
    agent = service.create_agent(data.dict())
    return agent.to_dict()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """获取代理详情"""
    service = ClawTeamService(db)
    agent = service.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    return agent.to_dict()


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, data: AgentUpdate, db: Session = Depends(get_db)):
    """更新代理"""
    service = ClawTeamService(db)
    agent = service.update_agent(agent_id, data.dict(exclude_unset=True))
    if not agent:
        raise HTTPException(status_code=404, detail="代理不存在")
    return agent.to_dict()


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    """删除代理"""
    service = ClawTeamService(db)
    success = service.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="代理不存在")
    return {"message": "代理已删除"}


# ========== 团队API ==========

@router.get("/teams")
async def get_teams(db: Session = Depends(get_db)):
    """获取所有团队"""
    service = ClawTeamService(db)
    teams = service.get_teams()
    return {"teams": [t.to_dict() for t in teams]}


@router.post("/teams")
async def create_team(data: TeamCreate, db: Session = Depends(get_db)):
    """创建团队"""
    service = ClawTeamService(db)
    team = service.create_team(data.dict())
    return team.to_dict()


@router.get("/teams/{team_id}")
async def get_team(team_id: str, db: Session = Depends(get_db)):
    """获取团队详情"""
    service = ClawTeamService(db)
    team = service.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    return team.to_dict()


@router.put("/teams/{team_id}")
async def update_team(team_id: str, data: TeamUpdate, db: Session = Depends(get_db)):
    """更新团队"""
    service = ClawTeamService(db)
    team = service.update_team(team_id, data.dict(exclude_unset=True))
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")
    return team.to_dict()


@router.delete("/teams/{team_id}")
async def delete_team(team_id: str, db: Session = Depends(get_db)):
    """删除团队"""
    service = ClawTeamService(db)
    success = service.delete_team(team_id)
    if not success:
        raise HTTPException(status_code=404, detail="团队不存在")
    return {"message": "团队已删除"}


# ========== 任务API ==========

@router.post("/teams/{team_id}/execute")
async def execute_task(team_id: str, data: TaskExecute, db: Session = Depends(get_db)):
    """执行团队任务"""
    service = ClawTeamService(db)
    try:
        task = await service.execute_task(team_id, data.description)
        return task.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tasks")
async def get_tasks(team_id: Optional[str] = None, db: Session = Depends(get_db)):
    """获取任务列表"""
    service = ClawTeamService(db)
    tasks = service.get_tasks(team_id)
    return {"tasks": [t.to_dict() for t in tasks]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, db: Session = Depends(get_db)):
    """获取任务详情"""
    service = ClawTeamService(db)
    task = service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task.to_dict()
