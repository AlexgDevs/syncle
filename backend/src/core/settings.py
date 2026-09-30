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

    # Price parsing (Playwright browser level, see docs/adr/ADR-004)
    PRICE_ENABLED: bool = True
    PRICE_HEADLESS: bool = False  # WB antibot blocks headless browsers
    PRICE_TIMEOUT: float = 45.0
    PROXY_URL: str = ""  # e.g. http://user:pass@host:port
    PROXY_ROTATE_URL: str = ""  # HTTP endpoint that swaps the proxy IP
    OPTIMAL_PRICE_UNDERCUT_PCT: float = 3.0

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
