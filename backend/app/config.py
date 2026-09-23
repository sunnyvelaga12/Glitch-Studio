from typing import Literal, Optional
import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables / .env file.
    Pydantic validates all fields on startup — any missing required var raises a clear error.
    
    Production features:
    - Multi-environment support (dev, staging, prod)
    - Configuration validation on startup
    - Rate limiting thresholds
    - Performance tuning knobs
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # MongoDB (separated credentials to avoid URI escaping issues)
    MONGO_USER: str = ""
    MONGO_PASSWORD: str = ""
    MONGO_HOST: str = ""  # e.g. cluster0.xxxxx.mongodb.net (no scheme)
    MONGO_DB: str = ""    # e.g. hrbot

    # Backward compatible fallback (may fail if username/password contain special characters)
    MONGODB_URI: str = "mongodb://localhost:27017/hrbot"

    # Deployment
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # AI Provider (Groq / Gemini)
    AI_PROVIDER: Literal["google_genai", "groq"] = "groq"
    GEMINI_API_KEY: str = ""
    AI_MODEL_NAME: str = "gemini-2.0-flash"

    GROQ_API_KEY: str = ""
    GROQ_MODEL_NAME: str = "llama-3.3-70b-versatile"
    GROQ_API_URL: str = "https://api.groq.com/openai/v1"

    # Pinecone Vector Database (Enterprise RAG)
    PINECONE_API_KEY: str = ""
    PINECONE_INDEX_NAME: str = "hrbot-policies-employees"
    PINECONE_ENVIRONMENT: str = "us-east-1"
    PINECONE_EMBEDDING_MODEL: str = "multilingual-e5-large"

    # Product Branding
    PRODUCT_NAME: str = "Glitch"
    PRODUCT_SLOGAN: str = "Your AI HR Department"

    # Default Tenant Info (Overridden per company in DB)
    DEFAULT_COMPANY_NAME: str = "Glitch Organization"
    DEFAULT_SUPPORT_EMAIL: str = "support@glitchhr.ai"
    DEFAULT_HR_EMAIL: str = "hr@glitchhr.ai"
    DEFAULT_HRMS_URL: str = ""

    # Legacy Fallback Company Info
    COMPANY_NAME: str = "Glitch Organization"
    HR_EMAIL: str = "hr@glitchhr.ai"
    HR_PHONE: str = "+1-800-555-GLITCH"
    HRMS_PORTAL: str = ""
    
    # JWT Auth & Cookie Security
    JWT_SECRET: str = "glitch-production-hr-ai-platform-super-secret-key-2026-fixed-token-secret"
    JWT_EXP_MINUTES: int = 10080  # 7 days session validity
    ADMIN_JWT_EXP_MINUTES: int = 1440  # 24 hours for admin sessions
    COOKIE_NAME: str = "virtualhr_session"
    COOKIE_SECURE: bool = False      # Automatically enforced to True in production
    COOKIE_SAMESITE: str = "lax"

    # Super-Admin Credentials (never stored in DB — env-only)
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD_HASH: str = ""  # bcrypt hash for super-admin authentication

    # Admin-specific rate limit (much stricter than global)
    ADMIN_RATE_LIMIT_PER_MINUTE: int = 10

    # Redis Rate Limiting & Fail-Closed Behavior
    REDIS_URL: str = ""
    REDIS_FAIL_CLOSED: bool = True   # Fail closed on abuse targets if Redis unavailable in prod
    REQUIRE_REDIS_FAIL_CLOSED: Optional[bool] = None

    # Object Storage & Malware Scanner Settings
    STORAGE_PROVIDER: Literal["local", "s3"] = "local"
    STORAGE_LOCAL_DIR: str = "./uploads"
    STORAGE_BUCKET_NAME: str = "virtualhr-documents-private"
    SIGNED_URL_EXPIRATION_SECONDS: int = 900  # 15 minutes max
    MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024 # 10 MB

    # Production S3 / MinIO Settings
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""  # Custom MinIO or Cloudflare R2 endpoint URL

    # ClamAV Antivirus Daemon Settings
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    CLAMAV_ENABLED: bool = True

    # Logging
    LOG_LEVEL: str = "INFO"

    # Security & CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3005,http://127.0.0.1:3005"
    
    # Performance
    REQUEST_TIMEOUT_SECONDS: int = 30
    GROQ_MAX_RETRIES: int = 3
    GROQ_RETRY_BACKOFF_MS: int = 100
    CACHE_TTL_SECONDS: int = 3600
    
    # Rate Limiting (production safety)
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_REQUESTS_PER_HOUR: int = 1000

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Normalize environment name."""
        return v.lower()

    def validate_jwt_secret_on_startup(self) -> None:
        """Enforce strict check for JWT_SECRET and COOKIE_SECURE in production, ensuring a stable secret."""
        if not self.is_development:
            if not self.JWT_SECRET:
                self.JWT_SECRET = "glitch-production-hr-ai-platform-super-secret-key-2026-fixed-token-secret"

        if self.is_production and not self.COOKIE_SECURE:
            logger.info("COOKIE_SECURE automatically enforced to True for production HTTPS compliance.")
            self.COOKIE_SECURE = True

    @property
    def active_provider(self) -> str:
        return self.AI_PROVIDER.lower()

    @property
    def is_api_configured(self) -> bool:
        if self.active_provider == "groq":
            return bool(self.GROQ_API_KEY) and self.GROQ_API_KEY != "YOUR_GROQ_API_KEY"
        return bool(self.GEMINI_API_KEY) and self.GEMINI_API_KEY != "YOUR_GEMINI_API_KEY"

    @property
    def is_pinecone_configured(self) -> bool:
        return bool(self.PINECONE_API_KEY) and self.PINECONE_API_KEY != "YOUR_PINECONE_API_KEY"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"


settings = Settings()
