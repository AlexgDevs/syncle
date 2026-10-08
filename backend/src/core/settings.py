from functools import lru_cache
from pathlib import Path

from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_ignore_empty=True,
        extra="ignore",
    )

    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    BOT_TOKEN: str
    LOG_LEVEL: str = "INFO"

    # LLM (OpenAI-compatible gateway, e.g. ProxyAPI)
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.proxyapi.ru/openai/v1"
    LLM_MODEL: str = ""
    LLM_TIMEOUT: float = 30.0
    # Vision-capable model for photo input (#27); "" falls back to LLM_MODEL,
    # and when both are empty vision is unavailable (bot degrades to text-only)
    LLM_VISION_MODEL: str = ""

    # Shared outbound HTTP (src.core.http): retry with backoff on timeouts/5xx
    HTTP_TIMEOUT: float = 10.0
    HTTP_MAX_RETRIES: int = 2
    HTTP_BACKOFF_BASE: float = 0.5

    # Redis (local instance; Taskiq broker and job state)
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 10
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_SOCKET_CONNECT_TIMEOUT: float = 5.0
    REDIS_RETRY_ON_TIMEOUT: bool = False

    # Background jobs: "inline" keeps the fast awaited path,
    # "taskiq" submits long analyses to the Taskiq/Redis worker (#38)
    JOBS_MODE: str = "inline"
    JOBS_POLL_INTERVAL: float = 2.0

    # Price parsing (Playwright browser level, see docs/adr/ADR-004)
    PRICE_ENABLED: bool = True
    PRICE_HEADLESS: bool = False  # WB antibot blocks headless browsers
    PRICE_TIMEOUT: float = 45.0
    PROXY_URL: str = ""  # e.g. http://user:pass@host:port
    PROXY_ROTATE_URL: str = ""  # HTTP endpoint that swaps the proxy IP
    OPTIMAL_PRICE_UNDERCUT_PCT: float = 3.0

    # Ozon parsing goes through a real Edge session (CDP) because Ozon
    # rejects plain HTTP clients with a JS bot challenge
    OZON_CDP_URL: str = "http://127.0.0.1:9336"

    # Reviews extraction (feedbacks2.wb.ru returns a single batch per
    # request; the cap is applied client-side)
    REVIEWS_CAP: int = 50

    # Deep niche scan (#39): listing items per marketplace. WB serves 100
    # items per search page, Ozon 8 per tile page (4 pages cover the cap).
    NICHE_ITEM_CAP: int = 30

    @computed_field  # type: ignore
    @property
    def DATABASE_URL(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_HOST,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore
