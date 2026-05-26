# config/settings.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_URL: str
    DEBUG: bool = False

    # ── Data filters ──────────────────────────────────────────────
    # Only listings from this year onwards are kept throughout the
    # entire pipeline: scraping → cleaning → loading → API.
    MIN_YEAR: int = 2018
    MAX_YEAR: int = 2026          # updated each year; prevents parser bugs like year=3008

    # ── Currency ──────────────────────────────────────────────────
    # KES per 1 USD.  Update this when the rate moves significantly.
    # The cost engine stores the rate it used at calculation time
    # (ic.usd_to_kes) so historical records stay internally consistent
    # even if you change this value later.
    USD_TO_KES: float = 130.0

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()