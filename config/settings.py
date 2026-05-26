# config/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_URL: str
    DEBUG: bool = False

    
    MIN_YEAR: int = 2018
    MAX_YEAR: int = 2026          
    USD_TO_KES: float = 130.0

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()