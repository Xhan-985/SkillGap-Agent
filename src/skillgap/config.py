"""全局配置（pydantic-settings，环境变量优先，支持 .env）。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://skillgap:skillgap@localhost:5432/skillgap"
    test_database_url: str = "postgresql://skillgap:skillgap@localhost:5432/skillgap_test"

    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_base_url: str = "https://api.adzuna.com/v1/api/jobs"
    adzuna_daily_quota: int = 250  # 免费层 250 req/day（DATA_GOVERNANCE §6，2026-08-31 核查）

    # Phase 3: LLM Gateway（OpenAI-compatible 单实现——用户决策 DeepSeek 2026-08-31）
    llm_base_url: str = "https://api.deepseek.com"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_timeout: float = 60.0     # API.md §0：LLM 相关 60s
    llm_max_retries: int = 2      # ADR-009：失败重试 ≤2 次后明示


settings = Settings()
