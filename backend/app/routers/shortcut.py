"""The endpoint behind the iPhone "Save to Reelish" shortcut.

iOS only lets App Store apps put their own icon in the share sheet, but any Apple Shortcut
can appear there too. The shortcut posts whatever was shared (a TikTok, Reel or Short) to
this endpoint with the user's private share key, then shows the returned `message` as a
notification. No copying links, no opening the app.

Every response, including errors, is JSON with a `message` the shortcut can show as-is.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..jobs import enqueue_video
from ..models import User, Video
from ..services import social
from ..services.pipeline import process_video
from ..services.sharing import create_link_video

router = APIRouter(prefix="/api/shortcut", tags=["iPhone shortcut"])

KEY_PREFIX = "rk_"
_POLL_SECONDS = 0.5


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_share_key(user: User) -> str:
    """Create (or replace) the user's share key. Returns the key; only its hash is kept."""
    key = KEY_PREFIX + secrets.token_urlsafe(24)
    user.share_key_hash = hash_key(key)
    user.share_key_hint = key[-4:]
    user.share_key_created_at = datetime.now(UTC)
    return key


def _reply(code: int, message: str, **extra) -> JSONResponse:
    return JSONResponse({"ok": code < 400, "message": message, **extra}, status_code=code)


def _short(title: str, limit: int = 60) -> str:
    title = " ".join(title.split())
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def _key_from(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-reelish-key", "").strip()


async def _shared_text(request: Request) -> str:
    """Accept JSON, a form, or a plain-text body. Shortcuts can send any of these."""
    ctype = request.headers.get("content-type", "")
    raw = await request.body()
    if "application/json" in ctype:
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            return ""
        if isinstance(data, dict):
            return " ".join(str(data.get(k) or "") for k in ("url", "text", "input")).strip()
        return str(data)
    if "form" in ctype:
        form = await request.form()
        return " ".join(str(form.get(k) or "") for k in ("url", "text", "input")).strip()
    return raw.decode("utf-8", "replace").strip()


def _wait_for(db: Session, video_id: int) -> Video:
    """Give the recipe a few seconds to finish so the notification can say what was added."""
    if not settings.redis_url:
        # No worker queue (local dev): just do the work now.
        process_video(video_id)
    else:
        deadline = time.monotonic() + settings.shortcut_wait_seconds
        while time.monotonic() < deadline:
            db.expire_all()
            if db.get(Video, video_id).status in ("done", "failed"):
                break
            time.sleep(_POLL_SECONDS)
    db.expire_all()
    return db.get(Video, video_id)


def _describe(video: Video) -> tuple[int, str, dict]:
    recipe = video.recipe
    if video.status == "failed":
        return 200, f"Saved, but Reelish couldn't read it: {video.error}", {"status": "failed"}
    if video.status != "done" or recipe is None:
        return 200, "Saved to Reelish. The ingredients will be on your list in a moment.", {"status": "processing"}
    extra = {"status": "done", "recipe_id": recipe.id, "title": recipe.title,
             "ingredient_count": len(recipe.ingredients)}
    title = _short(recipe.title)
    n = len(recipe.ingredients)
    if n == 0:
        return 200, f"Saved {title}, but it doesn't list ingredients. Add them in Reelish.", extra
    if any(gl.is_default for gl in recipe.lists):
        note = " Check the amounts." if recipe.estimated else ""
        return 200, f"Added {title} to your list ({n} ingredient{'s' if n != 1 else ''}).{note}", extra
    return 200, f"Saved {title} to your recipes.", extra


@router.post("/save")
async def save_shared(request: Request):
    key = _key_from(request)
    text = await _shared_text(request)
    # The work below blocks (database, waiting for the recipe), so keep it off the event loop.
    return await run_in_threadpool(_save, key, text)


def _save(key: str, text: str) -> JSONResponse:
    if not key.startswith(KEY_PREFIX):
        return _reply(status.HTTP_401_UNAUTHORIZED,
                      "This shortcut isn't connected to your account. Get your key in Reelish → Settings.")
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.share_key_hash == hash_key(key)))
        if user is None:
            return _reply(status.HTTP_401_UNAUTHORIZED,
                          "Your Reelish key has changed. Reinstall the shortcut from Reelish → Settings.")
        try:
            video, created = create_link_video(db, user, text)
        except social.LinkError as exc:
            return _reply(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Reelish couldn't save that. {exc}.")

        if not created:
            db.expire_all()
            video = db.get(Video, video.id)
            if video.recipe is not None:
                return _reply(200, f"Already saved: {_short(video.recipe.title)}.", status="done",
                              recipe_id=video.recipe.id, title=video.recipe.title, duplicate=True)
            return _reply(200, "Already saved. Reelish is still reading it.", status=video.status, duplicate=True)

        if settings.redis_url:
            enqueue_video(video.id, None)
        code, message, extra = _describe(_wait_for(db, video.id))
        return _reply(code, message, **extra)
    finally:
        db.close()
