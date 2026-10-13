"""File storage behind a tiny interface, so swapping in S3 later touches one file."""
from __future__ import annotations

import uuid
from pathlib import Path

from .config import settings

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def save(data_chunks, original_name: str, max_bytes: int) -> str:
    ext = Path(original_name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type {ext or '(none)'}; upload an mp4, mov or webm")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    key = f"{uuid.uuid4().hex}{ext}"
    path = settings.upload_dir / key
    size = 0
    try:
        with path.open("wb") as fh:
            for chunk in data_chunks:
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError(f"File is larger than {max_bytes // (1024 * 1024)} MB")
                fh.write(chunk)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    if size == 0:
        path.unlink(missing_ok=True)
        raise ValueError("File is empty")
    return key


def path_for(key: str) -> Path:
    return settings.upload_dir / key


def delete(key: str) -> None:
    path_for(key).unlink(missing_ok=True)
