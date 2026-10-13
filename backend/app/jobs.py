"""Enqueue video processing on Redis/RQ when configured, else run it after the response."""
from fastapi import BackgroundTasks

from .config import settings
from .services.pipeline import process_video


def enqueue_video(video_id: int, background: BackgroundTasks) -> None:
    if settings.redis_url:
        from redis import Redis
        from rq import Queue

        Queue("videos", connection=Redis.from_url(settings.redis_url)).enqueue(
            process_video, video_id, job_timeout=900)
    else:
        background.add_task(process_video, video_id)
