"""The background job: one shared video or link in, one recipe out, ingredients onto the list."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from .. import storage
from ..db import SessionLocal
from ..models import Ingredient, Recipe, User, Video
from . import social
from .extraction import extract_recipe
from .lists import add_recipe, get_default_list, rebuild_lists_for
from .media import MediaError, video_to_text
from .units import normalize_unit, parse_quantity

log = logging.getLogger(__name__)


def _gather_text(video: Video, workdir: Path) -> None:
    """Fill in video.caption / transcript / thumbnail from whatever sources are available."""
    if video.kind == "link":
        try:
            info = social.fetch_link_info(video.source_url, video.platform)
        except social.LinkError as exc:
            # Keep going if the user typed a caption; otherwise this is the error to show.
            if not video.caption.strip():
                raise ValueError(f"{exc} You can also paste the caption and retry.") from exc
            log.warning("video %s: %s", video.id, exc)
            info = social.LinkInfo()
        if info.caption and info.caption not in video.caption:
            video.caption = f"{info.caption}\n{video.caption}".strip()
        video.author = video.author or info.author
        video.thumbnail_url = video.thumbnail_url or info.thumbnail_url
        downloaded = social.download_video(video.source_url, workdir)
        source = downloaded
    else:
        source = storage.path_for(video.storage_key)

    if source is not None:
        try:
            video.transcript = video_to_text(source, workdir)
        except MediaError as exc:
            # A bad audio track shouldn't sink the job: the caption may be enough.
            log.warning("video %s: %s", video.id, exc)


def process_video(video_id: int, session_factory=SessionLocal) -> None:
    db: Session = session_factory()
    try:
        video = db.get(Video, video_id)
        if video is None or video.status not in ("uploaded", "failed"):
            return  # deleted, or another worker already took it
        video.status, video.error = "processing", ""
        db.commit()

        with tempfile.TemporaryDirectory() as tmp:
            _gather_text(video, Path(tmp))
        db.commit()

        if not video.caption.strip() and not video.transcript.strip():
            hint = ("Instagram doesn't share captions without setup. Paste the caption and retry."
                    if video.platform == "instagram" else
                    "No speech or caption found. Paste the caption and retry.")
            raise ValueError(hint)

        extracted = extract_recipe(video.caption, video.transcript)

        # Retrying updates the same recipe in place, so lists that contain it stay linked.
        recipe = video.recipe or Recipe(user_id=video.user_id, video_id=video.id)
        recipe.title = extracted.title[:255]
        recipe.servings = extracted.servings
        recipe.steps = extracted.steps
        recipe.reviewed = False
        recipe.estimated = extracted.estimated
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
