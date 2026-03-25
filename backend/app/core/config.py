"""
KAM 应用配置
"""
import json
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    APP_NAME: str = "KAM"
    APP_VERSION: str = "2.0.0"
    APP_DEBUG: bool = False
    APP_CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://localhost:8000"

    DATABASE_URL: str = "sqlite:///./storage/dev.db"
    STORAGE_PATH: str = "./storage"

    AGENT_WORKROOT: str = "./storage/agent-runs"
    CODEX_CLI_PATH: str = "codex"
    CLAUDE_CODE_CLI_PATH: str = "claude"

    DEFAULT_RUN_AGENT: str = "codex"
    ROUTER_MODEL: str = "gpt-5.4"
    ROUTER_REASONING_EFFORT: str = "xhigh"
    CODEX_MODEL: str = "gpt-5.4"
    CODEX_REASONING_EFFORT: str = "xhigh"

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        case_sensitive=True,
        extra="ignore",
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
