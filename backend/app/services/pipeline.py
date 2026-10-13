"""The background job: one uploaded video in, one draft recipe out."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from .. import storage
from ..db import SessionLocal
from ..models import Ingredient, Recipe, Video
from .extraction import extract_recipe
from .media import MediaError, video_to_text
from .units import normalize_unit, parse_quantity

log = logging.getLogger(__name__)


def process_video(video_id: int, session_factory=SessionLocal) -> None:
    db: Session = session_factory()
    try:
        video = db.get(Video, video_id)
        if video is None or video.status not in ("uploaded", "failed"):
            return  # deleted, or another worker already took it
        video.status, video.error = "processing", ""
        db.commit()

        try:
            with tempfile.TemporaryDirectory() as tmp:
                video.transcript = video_to_text(storage.path_for(video.storage_key), Path(tmp))
        except MediaError as exc:
            # A bad audio track shouldn't sink the job: the caption may be enough.
            log.warning("video %s: %s", video_id, exc)
            video.transcript = ""

        if not video.caption.strip() and not video.transcript.strip():
            raise ValueError("No speech or caption found. Paste the caption and retry.")

        extracted = extract_recipe(video.caption, video.transcript)
        if video.recipe is not None:  # retry: replace the old draft
            db.delete(video.recipe)
            db.flush()
        recipe = Recipe(user_id=video.user_id, video_id=video.id, title=extracted.title,
                        servings=extracted.servings, steps=extracted.steps, reviewed=False)
        recipe.ingredients = [
            Ingredient(position=i, name=ing.name[:255], quantity=parse_quantity(ing.quantity),
                       unit=normalize_unit(ing.unit), raw_text=ing.raw_text or ing.name)
            for i, ing in enumerate(extracted.ingredients)
        ]
        db.add(recipe)
        video.status = "done"
        if not extracted.ingredients:
            video.error = "No ingredients detected. Add them on the review screen."
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
