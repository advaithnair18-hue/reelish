"""Shared links from TikTok, Instagram and YouTube Shorts.

By default this only uses each platform's official oEmbed endpoint, which returns
public metadata (the caption, creator and a thumbnail) and is meant for apps that
embed or link to posts. Downloading the video itself is opt-in (ENABLE_VIDEO_DOWNLOAD).
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
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
                                    headers={"User-Agent": "ReelGroceries/1.0"})
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
    """Opt-in: fetch the video so its speech can be transcribed. Returns None if unavailable."""
    if not settings.enable_video_download or not shutil.which("yt-dlp"):
        return None
    out = dest_dir / "shared.%(ext)s"
    result = subprocess.run(
        ["yt-dlp", "--no-playlist", "-f", "mp4/best[height<=720]", "--max-filesize", "200M",
         "-o", str(out), url],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        log.warning("yt-dlp failed for %s: %s", url, result.stderr[-300:])
        return None
    files = sorted(dest_dir.glob("shared.*"))
    return files[0] if files else None
