"""
应用配置
"""
import json
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "AI工作助手"
    APP_VERSION: str = "1.0.0"
    APP_DEBUG: bool = False
    APP_SECRET_KEY: str = "your-secret-key-change-in-production"

    # CORS
    APP_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # 数据库
    DATABASE_URL: str = "sqlite:///./storage/dev.db"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_MODEL: str = "gpt-4"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"

    # Azure OpenAI (可选)
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_KEY: Optional[str] = None
    AZURE_OPENAI_VERSION: str = "2024-02-01"

    # 文件存储
    STORAGE_PATH: str = "./storage"
    MAX_UPLOAD_SIZE: int = 50 * 1024 * 1024  # 50MB

    # Agent 运行时
    AGENT_WORKROOT: str = "./storage/agent-runs"
    CODEX_CLI_PATH: str = "codex"
    CLAUDE_CODE_CLI_PATH: str = "claude"

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        case_sensitive=True,
    )

    @property
    def app_cors_origins_list(self) -> List[str]:
        text = self.APP_CORS_ORIGINS.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                return [str(origin).strip() for origin in json.loads(text) if str(origin).strip()]
            except json.JSONDecodeError:
                pass
        return [origin.strip() for origin in text.split(",") if origin.strip()]


settings = Settings()
