"""
Azure DevOps服务
"""
from typing import List, Dict, Any, Optional
import base64
import httpx
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.ado_config import ADOConfig


class ADOService:
    """Azure DevOps服务类"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_config(self, config_id: str) -> Optional[ADOConfig]:
        """获取配置"""
        return self.db.query(ADOConfig).filter(ADOConfig.id == config_id).first()
    
    def get_configs(self) -> List[ADOConfig]:
        """获取所有配置"""
        return self.db.query(ADOConfig).filter(ADOConfig.is_active == True).all()
    
    def create_config(self, data: Dict[str, Any]) -> ADOConfig:
        """创建配置"""
        config = ADOConfig(
            name=data["name"],
            server_url=data["server_url"],
            collection=data.get("collection", "DefaultCollection"),
            project=data["project"],
            auth_type=data.get("auth_type", "pat"),
            credentials=data.get("credentials", {}),
            scopes=data.get("scopes", ["vso.work", "vso.code", "vso.build"]),
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config
    
    def update_config(self, config_id: str, data: Dict[str, Any]) -> Optional[ADOConfig]:
        """更新配置"""
        config = self.get_config(config_id)
        if not config:
            return None
        
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        config.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(config)
        return config
    
    def delete_config(self, config_id: str) -> bool:
        """删除配置"""
        config = self.get_config(config_id)
        if config:
            self.db.delete(config)
            self.db.commit()
            return True
        return False
    
    def _get_auth_header(self, config: ADOConfig) -> Dict[str, str]:
        """获取认证头"""
        if config.auth_type == "pat":
            pat = config.credentials.get("pat", "")
            encoded = base64.b64encode(f":{pat}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        elif config.auth_type == "oauth":
            token = config.credentials.get("access_token", "")
            return {"Authorization": f"Bearer {token}"}
        else:
            return {}
    
    async def _make_request(
        self,
        config: ADOConfig,
        endpoint: str,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """发送API请求"""
        base_url = config.server_url.rstrip("/")
        if ".visualstudio.com" in base_url or "dev.azure.com" in base_url:
            # Azure DevOps Services
            url = f"{base_url}/{config.project}/_apis/{endpoint}"
        else:
            # Azure DevOps Server (TFS)
            url = f"{base_url}/{config.collection}/{config.project}/_apis/{endpoint}"
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self._get_auth_header(config),
        }
        
        params = params or {}
        params["api-version"] = "7.0"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json()
    
    async def get_work_items(
        self,
        config_id: str,
        query: Optional[str] = None,
        top: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        获取工作项
        
        Args:
            config_id: 配置ID
            query: WIQL查询语句
            top: 最大返回数量
        
        Returns:
            工作项列表
        """
        config = self.get_config(config_id)
        if not config:
            raise ValueError("配置不存在")
        
        try:
            # 使用默认查询或自定义查询
            if not query:
                query = "SELECT [System.Id] FROM workitems WHERE [System.TeamProject] = @Project"
            
            # 执行WIQL查询
            wiql_url = "wit/wiql"
            wiql_data = {"query": query}
            
            base_url = config.server_url.rstrip("/")
            if ".visualstudio.com" in base_url or "dev.azure.com" in base_url:
                url = f"{base_url}/{config.project}/_apis/{wiql_url}"
            else:
                url = f"{base_url}/{config.collection}/{config.project}/_apis/{wiql_url}"
            
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                **self._get_auth_header(config),
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    headers=headers,
                    json=wiql_data,
                    params={"api-version": "7.0"},
                    timeout=30.0,
                )
                response.raise_for_status()
                result = response.json()
            
            work_item_ids = [item["id"] for item in result.get("workItems", [])[:top]]
            
            if not work_item_ids:
                return []
            
            # 获取工作项详情
            ids_str = ",".join(map(str, work_item_ids))
            details = await self._make_request(
                config,
                f"wit/workitems",
                {"ids": ids_str, "$expand": "all"},
            )
            
            return details.get("value", [])
        
        except Exception as e:
            print(f"获取工作项失败: {e}")
            return []
    
    async def get_repositories(self, config_id: str) -> List[Dict[str, Any]]:
        """获取代码仓库列表"""
        config = self.get_config(config_id)
        if not config:
            raise ValueError("配置不存在")
        
        try:
            result = await self._make_request(config, "git/repositories")
            return result.get("value", [])
        except Exception as e:
            print(f"获取仓库失败: {e}")
            return []
    
    async def get_builds(
        self,
        config_id: str,
        top: int = 20,
    ) -> List[Dict[str, Any]]:
        """获取构建列表"""
        config = self.get_config(config_id)
        if not config:
            raise ValueError("配置不存在")
        
        try:
            result = await self._make_request(
                config,
                "build/builds",
                {"$top": top},
            )
            return result.get("value", [])
        except Exception as e:
            print(f"获取构建失败: {e}")
            return []
    
    async def test_connection(self, config_id: str) -> Dict[str, Any]:
        """测试连接"""
        config = self.get_config(config_id)
        if not config:
            return {"success": False, "error": "配置不存在"}
        
        try:
            # 尝试获取项目信息
            result = await self._make_request(config, "projects")
            return {
                "success": True,
                "projects": [p["name"] for p in result.get("value", [])],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
