from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "IELTS Vocab Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database
    DATABASE_URL: str = "sqlite:///./vocab.db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    SECRET_KEY: str = "change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # AI
    GOOGLE_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    
    # CORS — add your Vercel URL via CORS_ORIGINS env var in production
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000"]
    FRONTEND_URL: str = ""

    @property
    def all_cors_origins(self) -> list:
        origins = list(self.CORS_ORIGINS)
        if self.FRONTEND_URL:
            origins.append(self.FRONTEND_URL)
        return origins
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
