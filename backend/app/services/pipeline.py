"""The background job: one shared video or link in, one recipe out, ingredients onto the list."""
from __future__ import annotations

import logging
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from .. import storage
from ..config import settings
from ..db import SessionLocal
from ..models import Ingredient, Recipe, User, Video
from . import social
from .extraction import extract_recipe
from .lists import add_recipe, get_default_list, rebuild_lists_for
from .media import MediaError, VideoContent, analyze_video
from .units import normalize_unit, parse_quantity

log = logging.getLogger(__name__)


def _video_file(video: Video, workdir: Path) -> Path | None:
    """The video itself: a file the user uploaded or attached, else a download of the link."""
    if video.storage_key:
        path = storage.path_for(video.storage_key)
        if path.is_file():
            return path
        log.warning("video %s: stored file %s is gone", video.id, video.storage_key)
    if video.kind == "link":
        return social.download_video(video.source_url, workdir)
    return None


def _gather(video: Video, workdir: Path, timings: dict) -> VideoContent | None:
    """Fill in caption / creator / thumbnail, then watch and listen to the video if we can get it.
    The caption lookup and the video download run at the same time."""
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=2) as pool:
        info_job = (pool.submit(social.fetch_link_info, video.source_url, video.platform)
                    if video.kind == "link" else None)
        file_job = pool.submit(_video_file, video, workdir)
        source = file_job.result()
        timings["video"] = time.monotonic() - t0
        if info_job is not None:
            try:
                info = info_job.result()
            except social.LinkError as exc:
                # Keep going if there's a caption or a video; otherwise this is the error to show.
                if not video.caption.strip() and source is None:
                    raise ValueError(f"{exc} You can also paste the caption and retry.") from exc
                log.warning("video %s: %s", video.id, exc)
                info = social.LinkInfo()
            if info.caption and info.caption not in video.caption:
                video.caption = f"{info.caption}\n{video.caption}".strip()
            video.author = video.author or info.author
            video.thumbnail_url = video.thumbnail_url or info.thumbnail_url

    if source is None:
        return None
    t1 = time.monotonic()
    try:
        content = analyze_video(source, workdir)
    except MediaError as exc:
        log.warning("video %s: couldn't read the video file: %s", video.id, exc)
        return None
    finally:
        timings["analyse"] = time.monotonic() - t1
    video.transcript = content.transcript
    return content


def process_video(video_id: int, session_factory=SessionLocal) -> None:
    db: Session = session_factory()
    try:
        video = db.get(Video, video_id)
        if video is None or video.status not in ("uploaded", "failed"):
            return  # deleted, or another worker already took it
        video.status, video.error = "processing", ""
        db.commit()

        started, timings = time.monotonic(), {}
        with tempfile.TemporaryDirectory() as tmp:
            content = _gather(video, Path(tmp), timings)
        db.commit()
        # Frames only help when the AI is on to look at them.
        frames = content.frames if content and settings.anthropic_api_key else []
        watched = bool(frames or (content and content.transcript))

        if not video.caption.strip() and not video.transcript.strip() and not frames:
            hint = ("Instagram doesn't share captions without setup. Paste the caption and retry."
                    if video.platform == "instagram" else
                    "No speech or caption found. Paste the caption and retry.")
            raise ValueError(hint)

        t_ai = time.monotonic()
        extracted = extract_recipe(video.caption, video.transcript, frames)
        timings["ai"] = time.monotonic() - t_ai

        # Retrying updates the same recipe in place, so lists that contain it stay linked.
        recipe = video.recipe or Recipe(user_id=video.user_id, video_id=video.id)
        recipe.title = extracted.title[:255]
        recipe.servings = extracted.servings
        recipe.steps = extracted.steps
        recipe.reviewed = False
        recipe.estimated = extracted.estimated
        recipe.watched = watched
        recipe.source_url, recipe.platform = video.source_url, video.platform
        recipe.author, recipe.thumbnail_url = video.author, video.thumbnail_url
        recipe.ingredients = [
            Ingredient(position=i, name=ing.name[:255], quantity=parse_quantity(ing.quantity),
                       unit=normalize_unit(ing.unit), raw_text=ing.raw_text or ing.name)
            for i, ing in enumerate(extracted.ingredients)
        ]
        db.add(recipe)
        db.flush()

        user = db.get(User, video.user_id)
        if extracted.ingredients and user is not None and user.auto_add and not recipe.lists:
            add_recipe(get_default_list(db, user), recipe)
        else:
            rebuild_lists_for(recipe)

        video.status = "done"
        log.info("video %s done in %.1fs (%s)", video.id, time.monotonic() - started,
                 ", ".join(f"{k} {v:.1f}s" for k, v in timings.items()))
        if not extracted.ingredients:
            video.error = "No ingredients found in this video. Add them on the recipe screen."
        db.commit()
    except Exception as exc:  # noqa: BLE001 - a job must always end in a terminal state
        db.rollback()
        video = db.get(Video, video_id)
        if video is not None:
            video.status, video.error = "failed", str(exc)[:500]
            db.commit()
        log.exception("video %s failed", video_id)
    finally:
        db.close()
