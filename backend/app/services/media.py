"""What a video says and shows: speech as text, plus a handful of still frames.

Each step degrades gracefully if its tool or key is missing, so a video still gets as far
as it can (caption only, caption + frames, or caption + frames + speech).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ..config import settings

log = logging.getLogger(__name__)


class MediaError(Exception):
    pass


@dataclass
class VideoContent:
    transcript: str = ""
    frames: list[bytes] = field(default_factory=list)  # JPEGs, in time order


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    if not shutil.which(cmd[0]):
        raise MediaError(f"{cmd[0]} is not installed")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise MediaError(f"{cmd[0]} failed: {result.stderr.strip()[:300] or 'unknown error'}")
    return result


def probe(video_path: Path) -> tuple[float, bool]:
    """(duration in seconds, has an audio track)."""
    out = _run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type",
                "-of", "json", str(video_path)], timeout=60).stdout
    data = json.loads(out or "{}")
    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except ValueError:
        duration = 0.0
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    return duration, has_audio


def frame_times(duration: float, count: int) -> list[float]:
    """Evenly spread timestamps, skipping the very start and end (intros, end cards)."""
    if count <= 0:
        return []
    if duration <= 0:
        return [0.0]
    start, end = duration * 0.05, duration * 0.95
    if count == 1:
        return [round(duration / 2, 2)]
    step = (end - start) / (count - 1)
    return [round(start + i * step, 2) for i in range(count)]


def sample_frames(video_path: Path, workdir: Path, duration: float, count: int | None = None) -> list[bytes]:
    """Small JPEG stills, so the AI can read on-screen text and see the ingredients."""
    count = settings.max_frames if count is None else count
    frames = []
    for i, t in enumerate(frame_times(duration, count)):
        out = workdir / f"frame_{i:02d}.jpg"
        try:
            _run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(video_path),
                  "-frames:v", "1", "-vf", f"scale='min({settings.frame_width},iw)':-2", "-q:v", "6", str(out)],
                 timeout=60)
        except MediaError as exc:
            log.warning("frame at %ss: %s", t, exc)
            continue
        if out.exists() and out.stat().st_size > 0:
            frames.append(out.read_bytes())
            out.unlink()
    return frames


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """Small mono MP3 (16 kHz, 32 kbps): plenty for speech, and quick to upload."""
    _run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path), "-vn", "-ac", "1",
          "-ar", "16000", "-b:a", "32k", str(out_path)])
    return out_path


_model = None


def _transcribe_locally(audio_path: Path) -> str | None:
    global _model
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return None
    if _model is None:
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    segments, _info = _model.transcribe(str(audio_path), vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def _transcribe_hosted(audio_path: Path, client: httpx.Client | None = None) -> str:
    """Any OpenAI-compatible transcription API (Groq by default)."""
    own = client is None
    client = client or httpx.Client(timeout=120)
    try:
        with audio_path.open("rb") as fh:
            resp = client.post(
                settings.transcribe_api_url,
                headers={"Authorization": f"Bearer {settings.transcribe_api_key}"},
                data={"model": settings.transcribe_model, "response_format": "json"},
                files={"file": (audio_path.name, fh, "audio/mpeg")},
            )
    finally:
        if own:
            client.close()
    if resp.status_code != 200:
        raise MediaError(f"transcription failed with HTTP {resp.status_code}")
    return str(resp.json().get("text") or "").strip()


def transcribe(audio_path: Path, client: httpx.Client | None = None) -> str:
    """Hosted speech-to-text if a key is set (fits small servers), else local Whisper if installed."""
    if settings.transcribe_api_key:
        return _transcribe_hosted(audio_path, client)
    local = _transcribe_locally(audio_path)
    if local is None:
        log.info("no speech-to-text configured; skipping the audio")
        return ""
    return local


def pick_evenly(items: list, count: int) -> list:
    """`count` items spread across the list, skipping the very first (often a title card)."""
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return list(items)
    pool = items[1:] if len(items) > count + 1 else items
    step = (len(pool) - 1) / (count - 1) if count > 1 else 0
    return [pool[round(i * step)] for i in range(count)] if count > 1 else [pool[len(pool) // 2]]


def keyframes_and_audio(video_path: Path, workdir: Path, has_audio: bool) -> tuple[list[Path], Path | None]:
    """One ffmpeg pass: decode only the key frames (cheap) for stills, and pull the audio out
    alongside. Much faster than seeking and decoding once per frame, which matters on small servers."""
    frames_dir = workdir / "kf"
    frames_dir.mkdir(exist_ok=True)
    audio = workdir / "audio.mp3" if has_audio else None
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-skip_frame", "nokey", "-i", str(video_path),
           "-map", "0:v:0", "-vf", f"scale='min({settings.frame_width},iw)':-2", "-fps_mode", "vfr",
           "-q:v", "6", str(frames_dir / "kf_%03d.jpg")]
    if audio is not None:
        cmd += ["-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(audio)]
    _run(cmd)
    return sorted(frames_dir.glob("kf_*.jpg")), audio


def analyze_video(video_path: Path, workdir: Path) -> VideoContent:
    started = time.monotonic()
    duration, has_audio = probe(video_path)
    keyframes, audio = keyframes_and_audio(video_path, workdir, has_audio)
    frames = [f.read_bytes() for f in pick_evenly(keyframes, settings.max_frames)]
    # Videos with very few key frames: fall back to seeking for evenly spaced stills.
    if len(frames) < min(3, settings.max_frames) and duration > 1:
        frames = sample_frames(video_path, workdir, duration)
    decoded = time.monotonic()
    content = VideoContent(frames=frames)
    if audio is not None and audio.exists():
        try:
            content.transcript = transcribe(audio)
        except (MediaError, httpx.HTTPError) as exc:
            log.warning("speech-to-text failed: %s", exc)
        finally:
            audio.unlink(missing_ok=True)
    log.info("video analysed: %.1fs of video, %d frames from %d key frames, decode %.1fs, speech %.1fs",
             duration, len(frames), len(keyframes), decoded - started, time.monotonic() - decoded)
    return content
