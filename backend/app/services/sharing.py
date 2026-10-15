"""Turning a shared link into a queued video, shared by the app and the iPhone shortcut."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import User, Video
from . import social


def create_link_video(db: Session, user: User, shared_text: str, caption: str = "") -> tuple[Video, bool]:
    """Returns (video, created). Raises social.LinkError for anything that isn't a supported video link.

    Share sheets send text like "Check this out! https://vm.tiktok.com/abc", so the link is
    pulled out of whatever arrives. Sharing the same post twice returns the existing video.
    """
    url = social.find_url(shared_text)
    if url is None:
        raise social.LinkError("No link found in what was shared")
    platform = social.detect_platform(url)
    existing = db.scalar(select(Video).where(Video.user_id == user.id, Video.source_url == url))
    if existing is not None:
        return existing, False
    video = Video(user_id=user.id, kind="link", source_url=url, platform=platform, caption=caption)
    db.add(video)
    db.commit()
    return video, True
