"""
ClawTeam服务 - AI代理团队协作
"""
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.agent import Agent, AgentTeam
from app.models.task import Task, SubTask
from app.services.llm_service import llm_service


class ClawTeamService:
    """ClawTeam服务类"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ========== 代理管理 ==========
    
    def get_agents(self) -> List[Agent]:
        """获取所有代理"""
        return self.db.query(Agent).filter(Agent.is_active == True).all()
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """获取单个代理"""
        return self.db.query(Agent).filter(Agent.id == agent_id).first()
    
    def create_agent(self, data: Dict[str, Any]) -> Agent:
        """创建代理"""
        agent = Agent(
            name=data["name"],
            role=data["role"],
            description=data.get("description"),
            capabilities=data.get("capabilities", []),
            system_prompt=data.get("system_prompt"),
            model=data.get("model", "gpt-4"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 2000),
            tools=data.get("tools", []),
        )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent
    
    def update_agent(self, agent_id: str, data: Dict[str, Any]) -> Optional[Agent]:
        """更新代理"""
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        
        for key, value in data.items():
            if hasattr(agent, key):
                setattr(agent, key, value)
        
        agent.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(agent)
        return agent
    
    def delete_agent(self, agent_id: str) -> bool:
        """删除代理"""
        agent = self.get_agent(agent_id)
        if agent:
            agent.is_active = False
            self.db.commit()
            return True
        return False
    
    # ========== 团队管理 ==========
    
    def get_teams(self) -> List[AgentTeam]:
        """获取所有团队"""
        return self.db.query(AgentTeam).filter(AgentTeam.is_active == True).all()
    
    def get_team(self, team_id: str) -> Optional[AgentTeam]:
        """获取单个团队"""
        return self.db.query(AgentTeam).filter(AgentTeam.id == team_id).first()
    
    def create_team(self, data: Dict[str, Any]) -> AgentTeam:
        """创建团队"""
        team = AgentTeam(
            name=data["name"],
            description=data.get("description"),
            topology=data.get("topology", "hierarchical"),
            coordinator_id=data.get("coordinator_id"),
        )
        self.db.add(team)
        self.db.commit()
        self.db.refresh(team)
        
        # 添加代理到团队
        if "agent_ids" in data:
            for agent_id in data["agent_ids"]:
                agent = self.get_agent(agent_id)
                if agent:
                    team.agents.append(agent)
            self.db.commit()
        
        return team
    
    def update_team(self, team_id: str, data: Dict[str, Any]) -> Optional[AgentTeam]:
        """更新团队"""
        team = self.get_team(team_id)
        if not team:
            return None
        
        for key, value in data.items():
            if key == "agent_ids":
                # 更新团队代理
                team.agents = []
                for agent_id in value:
                    agent = self.get_agent(agent_id)
                    if agent:
                        team.agents.append(agent)
            elif hasattr(team, key):
                setattr(team, key, value)
        
        team.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(team)
        return team
    
    def delete_team(self, team_id: str) -> bool:
        """删除团队"""
        team = self.get_team(team_id)
        if team:
            team.is_active = False
            self.db.commit()
            return True
        return False
    
    # ========== 任务执行 ==========
    
    async def execute_task(self, team_id: str, description: str) -> Task:
        """
        执行团队任务
        
        Args:
            team_id: 团队ID
            description: 任务描述
        
        Returns:
            任务对象
        """
        team = self.get_team(team_id)
        if not team:
            raise ValueError("团队不存在")
        
        # 创建任务
        task = Task(
            team_id=team_id,
            description=description,
            status="running",
            started_at=datetime.utcnow(),
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        
        try:
            # 根据团队拓扑执行
            if team.topology == "hierarchical":
                result = await self._execute_hierarchical(team, task, description)
            elif team.topology == "peer-to-peer":
                result = await self._execute_peer_to_peer(team, task, description)
            elif team.topology == "pipeline":
                result = await self._execute_pipeline(team, task, description)
            else:
                result = await self._execute_hierarchical(team, task, description)
            
            task.result = result
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            
        except Exception as e:
            task.status = "failed"
            task.result = f"执行失败: {str(e)}"
        
        self.db.commit()
        self.db.refresh(task)
        return task
    
    async def _execute_hierarchical(
        self,
        team: AgentTeam,
        task: Task,
        description: str,
    ) -> str:
        """层级式执行 (Manager-Worker)"""
        # 1. 规划者分解任务
        planner = self._get_agent_by_role(team, "planner")
        if planner:
            subtasks = await self._plan_task(planner, description)
        else:
            subtasks = [{"description": description}]
        
        # 创建子任务
        for i, subtask_data in enumerate(subtasks):
            subtask = SubTask(
                task_id=task.id,
                description=subtask_data["description"],
                complexity=subtask_data.get("complexity", 5),
                status="pending",
            )
            self.db.add(subtask)
        self.db.commit()
        
        # 2. 路由者分配任务
        router = self._get_agent_by_role(team, "router")
        if router:
            assignments = await self._assign_tasks(router, subtasks, team.agents)
        else:
            # 默认分配给第一个执行者
            executor = self._get_agent_by_role(team, "executor") or team.agents[0]
            assignments = [(executor, sub) for sub in subtasks]
        
        # 3. 执行者执行任务
        results = []
        for agent, subtask_data in assignments:
            subtask = self.db.query(SubTask).filter(
                SubTask.task_id == task.id,
                SubTask.description == subtask_data["description"]
            ).first()
            
            if subtask:
                subtask.status = "running"
                subtask.started_at = datetime.utcnow()
                subtask.assigned_agent_id = agent.id
                self.db.commit()
                
                result = await self._execute_subtask(agent, subtask.description)
                
                subtask.actual_output = result
                subtask.status = "completed"
                subtask.completed_at = datetime.utcnow()
                self.db.commit()
                
                results.append(result)
        
        # 4. 综合者整合结果
        synthesizer = self._get_agent_by_role(team, "synthesizer")
        if synthesizer and len(results) > 1:
            return await self._synthesize_results(synthesizer, results)
        
        return "\n\n".join(results) if results else "任务执行完成"
    
    async def _execute_peer_to_peer(
        self,
        team: AgentTeam,
        task: Task,
        description: str,
    ) -> str:
        """对等式执行 (代理直接协作)"""
        # 所有代理并行讨论
        messages = []
        
        for agent in team.agents:
            response = await self._agent_chat(agent, description, messages)
            messages.append({"agent": agent.name, "content": response})
        
        # 综合讨论结果
        return "\n\n".join([f"{m['agent']}: {m['content']}" for m in messages])
    
    async def _execute_pipeline(
        self,
        team: AgentTeam,
        task: Task,
        description: str,
    ) -> str:
        """管道式执行 (顺序处理)"""
        # 按角色顺序执行
        role_order = ["decomposer", "executor", "validator", "synthesizer"]
        
        current_input = description
        for role in role_order:
            agent = self._get_agent_by_role(team, role)
            if agent:
                current_input = await self._execute_subtask(agent, current_input)
        
        return current_input
    
    def _get_agent_by_role(self, team: AgentTeam, role: str) -> Optional[Agent]:
        """根据角色获取代理"""
        for agent in team.agents:
            if agent.role == role:
                return agent
        return None
    
    async def _plan_task(self, planner: Agent, description: str) -> List[Dict]:
        """规划者分解任务"""
        prompt = f"""作为任务规划者，请将以下任务分解为子任务。

任务描述: {description}

请以JSON格式输出子任务列表:
{{"subtasks": [{{"description": "子任务描述", "complexity": 1-10}}]}}"""

        try:
            response = await llm_service.chat_completion(
                messages=[
                    {"role": "system", "content": planner.system_prompt or "你是任务规划专家。"},
                    {"role": "user", "content": prompt},
                ],
                model=planner.model,
                temperature=planner.temperature,
            )
            
            import json
            result = json.loads(response["content"])
            return result.get("subtasks", [{"description": description, "complexity": 5}])
        except:
            return [{"description": description, "complexity": 5}]
    
    async def _assign_tasks(
        self,
        router: Agent,
        subtasks: List[Dict],
        agents: List[Agent],
    ) -> List[tuple]:
        """路由者分配任务"""
        agent_info = "\n".join([f"- {a.name} (角色: {a.role}, 能力: {', '.join(a.capabilities or [])})" for a in agents])
        
        prompt = f"""作为任务路由者，请将子任务分配给最合适的代理。

可用代理:
{agent_info}

子任务:
{chr(10).join([f"- {s['description']}" for s in subtasks])}

请以JSON格式输出分配结果:
{{"assignments": [{{"subtask_index": 0, "agent_name": "代理名称"}}]}}"""

        try:
            response = await llm_service.chat_completion(
                messages=[
                    {"role": "system", "content": router.system_prompt or "你是任务路由专家。"},
                    {"role": "user", "content": prompt},
                ],
                model=router.model,
                temperature=router.temperature,
            )
            
            import json
            result = json.loads(response["content"])
            assignments = []
            for assign in result.get("assignments", []):
                idx = assign.get("subtask_index", 0)
                agent_name = assign.get("agent_name", agents[0].name)
                agent = next((a for a in agents if a.name == agent_name), agents[0])
                if idx < len(subtasks):
                    assignments.append((agent, subtasks[idx]))
            
            return assignments if assignments else [(agents[0], subtasks[0])]
        except:
            return [(agents[0], subtasks[0])]
    
    async def _execute_subtask(self, agent: Agent, description: str) -> str:
        """执行子任务"""
        response = await llm_service.chat_completion(
            messages=[
                {"role": "system", "content": agent.system_prompt or f"你是{agent.role}。"},
                {"role": "user", "content": description},
            ],
            model=agent.model,
            temperature=agent.temperature,
            max_tokens=agent.max_tokens,
        )
        return response["content"]
    
    async def _synthesize_results(self, synthesizer: Agent, results: List[str]) -> str:
        """综合者整合结果"""
        prompt = f"""请将以下结果整合为一份完整的报告:

{chr(10).join([f"结果 {i+1}:\n{r}\n" for i, r in enumerate(results)])}"""

        response = await llm_service.chat_completion(
            messages=[
                {"role": "system", "content": synthesizer.system_prompt or "你是结果综合专家。"},
                {"role": "user", "content": prompt},
            ],
            model=synthesizer.model,
            temperature=synthesizer.temperature,
        )
        return response["content"]
    
    async def _agent_chat(self, agent: Agent, description: str, messages: List[Dict]) -> str:
        """代理参与讨论"""
        context = "\n".join([f"{m['agent']}: {m['content']}" for m in messages])
        
        prompt = f"""任务: {description}

之前的讨论:
{context}

请发表你的看法。"""

        response = await llm_service.chat_completion(
            messages=[
                {"role": "system", "content": agent.system_prompt or f"你是{agent.name}。"},
                {"role": "user", "content": prompt},
            ],
            model=agent.model,
            temperature=agent.temperature,
        )
        return response["content"]
    
    def get_tasks(self, team_id: Optional[str] = None) -> List[Task]:
        """获取任务列表"""
        query = self.db.query(Task)
        if team_id:
            query = query.filter(Task.team_id == team_id)
        return query.order_by(Task.created_at.desc()).all()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """获取单个任务"""
        return self.db.query(Task).filter(Task.id == task_id).first()
