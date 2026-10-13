"""App settings, read from environment variables with safe local defaults."""
import os
from pathlib import Path


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./reel_groceries.db")
        self.jwt_secret = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-production")
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
        # Instagram's official oEmbed needs a Meta app token; without it, Reels are saved
        # by link and you add the caption yourself.
        self.instagram_oembed_token = os.getenv("INSTAGRAM_OEMBED_TOKEN", "")
        # Opt-in: download the video behind a shared link with yt-dlp so speech can be
        # transcribed. Off by default; check each platform's terms before enabling.
        self.enable_video_download = os.getenv("ENABLE_VIDEO_DOWNLOAD", "").lower() in ("1", "true", "yes")
        # When a video names a dish but lists no ingredients, ask the LLM for a typical
        # ingredient list and mark the recipe "estimated".
        self.estimate_missing = os.getenv("ESTIMATE_MISSING_INGREDIENTS", "true").lower() in ("1", "true", "yes")
        self.cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")


settings = Settings()
