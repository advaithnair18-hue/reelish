"""Shared links from TikTok, Instagram and YouTube Shorts.

By default this only uses each platform's official oEmbed endpoint, which returns
public metadata (the caption, creator and a thumbnail) and is meant for apps that
embed or link to posts. Downloading the video itself is opt-in (ENABLE_VIDEO_DOWNLOAD).
"""
from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from ..config import settings

log = logging.getLogger(__name__)

PLATFORM_HOSTS = {
    "tiktok": ("tiktok.com",),
    "instagram": ("instagram.com", "instagr.am"),
    "youtube": ("youtube.com", "youtu.be"),
}

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


class LinkError(Exception):
    pass


@dataclass
class LinkInfo:
    caption: str = ""
    author: str = ""
    thumbnail_url: str = ""


def find_url(text: str) -> str | None:
    """Share sheets often send 'Check out this video! https://vm.tiktok.com/abc' — pull the URL out."""
    m = _URL_RE.search(text or "")
    return m.group(0).rstrip(".,!?)") if m else None


def detect_platform(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise LinkError("That doesn't look like a link") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        raise LinkError("That doesn't look like a link")
    for platform, suffixes in PLATFORM_HOSTS.items():
        if any(host == s or host.endswith("." + s) for s in suffixes):
            return platform
    raise LinkError("Share a TikTok, Instagram Reel or YouTube Short")


def _oembed_endpoint(platform: str, url: str) -> tuple[str, dict] | None:
    if platform == "tiktok":
        return "https://www.tiktok.com/oembed", {"url": url}
    if platform == "youtube":
        return "https://www.youtube.com/oembed", {"url": url, "format": "json"}
    if platform == "instagram" and settings.instagram_oembed_token:
        return "https://graph.facebook.com/v21.0/instagram_oembed", {
            "url": url, "access_token": settings.instagram_oembed_token,
            "fields": "title,author_name,thumbnail_url"}
    return None


def fetch_link_info(url: str, platform: str, client: httpx.Client | None = None) -> LinkInfo:
    endpoint = _oembed_endpoint(platform, url)
    if endpoint is None:
        return LinkInfo()
    own_client = client is None
    client = client or httpx.Client(timeout=15, follow_redirects=True,
                                    headers={"User-Agent": "Reelish/1.0"})
    try:
        resp = client.get(endpoint[0], params=endpoint[1])
        if resp.status_code != 200:
            raise LinkError(f"Couldn't read that post (HTTP {resp.status_code}). Is it public?")
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise LinkError("Couldn't reach the platform to read that post") from exc
    finally:
        if own_client:
            client.close()
    return LinkInfo(caption=str(data.get("title") or "").strip(),
                    author=str(data.get("author_name") or "").strip(),
                    thumbnail_url=str(data.get("thumbnail_url") or "").strip())


def download_video(url: str, dest_dir: Path) -> Path | None:
    """Download the shared video so the AI can watch and hear it. Returns None if unavailable.

    Runs yt-dlp in-process (no extra Python start-up) and asks for a small version of the
    video: 540p is plenty for reading on-screen text, and downloads and decodes faster.
    """
    if not settings.enable_video_download or importlib.util.find_spec("yt_dlp") is None:
        return None
    from yt_dlp import YoutubeDL

    opts = {
        "format": "b[ext=mp4][height<=540]/b[height<=540]/b[ext=mp4]/b",
        "outtmpl": str(dest_dir / "shared.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 15,
        "retries": 1,
        "max_filesize": 150 * 1024 * 1024,
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except Exception as exc:  # noqa: BLE001 - any failure means "couldn't download", never a crash
        log.warning("download failed for %s: %s", url, str(exc)[:300])
        return None
    files = sorted(p for p in dest_dir.glob("shared.*") if not p.name.endswith(".part"))
    return files[0] if files else None
