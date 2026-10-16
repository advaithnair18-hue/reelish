"""RQ worker entry point: `python worker.py` (needs REDIS_URL)."""
from redis import Redis
from rq import Worker

from app import models  # noqa: F401
from app.config import settings
from app.db import ensure_schema

if __name__ == "__main__":
    ensure_schema()
    Worker(["videos"], connection=Redis.from_url(settings.redis_url)).work()
