from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings"""
    
    # Application
    APP_NAME: str = "Reaum"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"
    
    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENCRYPTION_KEY: str
    
    # Database
    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    
    # Redis
    REDIS_URL: str
    REDIS_PASSWORD: Optional[str] = None
    
    # CORS
    ALLOWED_ORIGINS: List[str] = ["*"]
    ALLOW_CREDENTIALS: bool = True
    
    # File Upload
    MAX_FILE_SIZE_MB: int = 10
    UPLOAD_DIR: str = "./uploads"
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".csv", ".xlsx", ".xls"]
    
    # External APIs
    NSE_API_KEY: Optional[str] = None
    BSE_API_KEY: Optional[str] = None
    AMFI_API_URL: str = "https://www.amfiindia.com/spages/NAVAll.txt"
    RBI_FX_API_URL: str = "https://www.rbi.org.in/"
    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    
    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    SENTRY_DSN: Optional[str] = None
    
    # Financial Settings
    FINANCIAL_YEAR_START_MONTH: int = 4  # April
    FINANCIAL_YEAR_START_DAY: int = 1
    BASE_CURRENCY: str = "INR"
    
    # Scheduling
    PRICING_JOB_SCHEDULE: str = "0 18 * * 1-5"  # 6 PM on weekdays
    FX_RATE_SCHEDULE: str = "0 9,15 * * 1-5"   # 9 AM and 3 PM on weekdays
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


settings = get_settings()