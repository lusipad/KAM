from __future__ import annotations

from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from runtime_paths import bundle_root, is_frozen_runtime, runtime_path


def _default_database_url() -> str:
    return f"sqlite+aiosqlite:///{runtime_path('storage', 'kam-harness.db').as_posix()}"


def _default_storage_path() -> str:
    return str(runtime_path("storage"))


def _default_run_root() -> str:
    return str(runtime_path("storage", "runs"))


def _env_files() -> tuple[str, ...]:
    candidates = [
        runtime_path(".env"),
        bundle_root() / ".env",
        Path(".env"),
        Path("../.env"),
    ]
    values: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return tuple(values)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_files(), extra="ignore", case_sensitive=False)

    app_name: str = "KAM Harness"
    app_version: str = "3.0.0"
    app_env: str = "production" if is_frozen_runtime() else "development"
    app_debug: bool = False
    mock_runs: bool = False
    app_cors_origins: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173"

    database_url: str = _default_database_url()
    storage_path: str = _default_storage_path()
    run_root: str = _default_run_root()

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
