"""App settings, read from environment variables with safe local defaults."""
import os
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./reel_groceries.db")
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-secret-change-me")
        self.jwt_expire_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
        self.upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "200"))
        # If set, videos are processed by an RQ worker; otherwise in-process.
        self.redis_url = os.getenv("REDIS_URL", "")
        # If set, recipes are extracted with Claude; otherwise a rule-based parser.
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        # faster-whisper model size, used only if the package is installed.
        self.whisper_model = os.getenv("WHISPER_MODEL", "base")
        self.cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


settings = Settings()
