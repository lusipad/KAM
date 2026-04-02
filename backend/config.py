from __future__ import annotations

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore", case_sensitive=False)

    app_name: str = "KAM V3"
    app_version: str = "3.0.0"
    app_env: str = "development"
    app_debug: bool = False
    app_cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = "sqlite+aiosqlite:///./storage/kam-v3.db"
    storage_path: str = "./storage"
    run_root: str = "./storage/runs"

    anthropic_api_key: str = ""
    chat_model: str = "claude-sonnet-4-20250514"
    digest_model: str = "claude-sonnet-4-20250514"

    claude_code_path: str = "C:/Users/lus/AppData/Roaming/npm/claude.cmd"
    codex_path: str = "codex"

    github_token: str = ""
    azure_devops_pat: str = ""
    azure_devops_org: str = ""

    context_budget_tokens: int = 8000
    memory_always_inject_tokens: int = 500
    memory_search_tokens: int = 1500
    max_concurrent_runs: int = 3

    git_user_name: str = "KAM Bot"
    git_user_email: str = "kam@example.com"

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.app_cors_origins.split(",") if item.strip()]

    @computed_field
    @property
    def storage_dir(self) -> Path:
        return Path(self.storage_path).resolve()

    @computed_field
    @property
    def run_dir(self) -> Path:
        return Path(self.run_root).resolve()

    @computed_field
    @property
    def is_test_env(self) -> bool:
        return self.app_env.lower() == "test"


settings = Settings()
