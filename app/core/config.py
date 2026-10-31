from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Support & Logistics Assistant"
    ENVIRONMENT: str = "development"
    API_V1_STR: str = "/api/v1"

    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "support_assistant_db"

    JWT_SECRET_KEY: str = "dev-only-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 14
    COOKIE_SECURE: bool = False
    GOOGLE_CLIENT_ID: str = ""

    GOOGLE_API_KEY: str = ""
    LLM_MODEL: str = "gemini-2.5-flash"
    ROUTER_MODEL: str = "gemini-2.5-flash-lite"
    LLM_THINKING_BUDGET: int = 0
    AI_IMAGE_TRIAGE: bool = False

    PAYMENT_PROVIDER: str = "fake"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FAKE_WEBHOOK_DELAY_SECONDS: float = 2.0

    STORAGE_BACKEND: str = "local"
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "support-assistant"

    CRON_SECRET: str = "change-me"
    RATE_LIMIT_MESSAGES_PER_MINUTE: int = 12

    @property
    def is_prod(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
