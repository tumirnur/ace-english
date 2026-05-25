from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./adaptive_learning.db"
    project_root: Path = Path(__file__).resolve().parents[2]
    llm_api_key: str = ""


settings = Settings()
