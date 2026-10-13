"""Video -> audio -> text. Each step degrades gracefully if its tool is missing."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from ..config import settings

log = logging.getLogger(__name__)


class MediaError(Exception):
    pass


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """16 kHz mono WAV, which is what speech models expect."""
    if not shutil.which("ffmpeg"):
        raise MediaError("ffmpeg is not installed")
    result = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path), "-vn", "-ac", "1",
         "-ar", "16000", str(out_path)],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise MediaError(f"ffmpeg failed: {result.stderr.strip()[:300] or 'unknown error'}")
    return out_path


def has_audio_stream(video_path: Path) -> bool:
    if not shutil.which("ffprobe"):
        return True  # can't tell; let ffmpeg try
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=60,
    )
    return bool(result.stdout.strip())


_model = None


def transcribe(audio_path: Path) -> str:
    """Transcribe with faster-whisper if installed; otherwise return '' and rely on the caption."""
    global _model
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        log.info("faster-whisper not installed; skipping transcription")
        return ""
    if _model is None:
        _model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    segments, _info = _model.transcribe(str(audio_path), vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def video_to_text(video_path: Path, workdir: Path) -> str:
    if not has_audio_stream(video_path):
        return ""
    audio = extract_audio(video_path, workdir / f"{video_path.stem}.wav")
    try:
        return transcribe(audio)
    finally:
        audio.unlink(missing_ok=True)
