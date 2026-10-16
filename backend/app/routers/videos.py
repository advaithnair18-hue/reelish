from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import storage
from ..auth import current_user
from ..config import settings
from ..db import get_db
from ..jobs import enqueue_video
from ..models import User, Video
from ..schemas import LinkIn, VideoOut
from ..services import social
from ..services.sharing import create_link_video

router = APIRouter(prefix="/api/videos", tags=["videos"])


def _out(v: Video) -> VideoOut:
    out = VideoOut.model_validate(v)
    out.recipe_id = v.recipe.id if v.recipe else None
    return out


def _owned(db: Session, video_id: int, user: User) -> Video:
    video = db.get(Video, video_id)
    # 404 rather than 403 for other users' videos, so ids can't be probed.
    if video is None or video.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Video not found")
    return video


def _chunks(upload: UploadFile, size: int = 1024 * 1024):
    while chunk := upload.file.read(size):
        yield chunk


@router.post("", response_model=VideoOut, status_code=status.HTTP_202_ACCEPTED)
def upload_video(background: BackgroundTasks, file: UploadFile = File(...),
                 caption: str = Form("", max_length=10000),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    try:
        key = storage.save(_chunks(file), file.filename or "", settings.max_upload_mb * 1024 * 1024)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    video = Video(user_id=user.id, storage_key=key, original_filename=(file.filename or "")[:255],
                  caption=caption)
    db.add(video)
    db.commit()
    enqueue_video(video.id, background)
    return _out(video)


@router.post("/link", response_model=VideoOut, status_code=status.HTTP_202_ACCEPTED)
def share_link(body: LinkIn, background: BackgroundTasks,
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    """What the in-app share flow calls: a TikTok, Reel or Short link (or text containing one)."""
    try:
        video, created = create_link_video(db, user, body.url, body.caption)
    except social.LinkError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if created:
        enqueue_video(video.id, background)
    return _out(video)


@router.get("", response_model=list[VideoOut])
def list_videos(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Video).where(Video.user_id == user.id)
                      .order_by(Video.created_at.desc(), Video.id.desc()).limit(limit).offset(offset))
    return [_out(v) for v in rows]


@router.get("/{video_id}", response_model=VideoOut)
def get_video(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _out(_owned(db, video_id, user))


@router.post("/{video_id}/retry", response_model=VideoOut, status_code=status.HTTP_202_ACCEPTED)
def retry_video(video_id: int, background: BackgroundTasks, caption: str | None = Form(None),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    video = _owned(db, video_id, user)
    if video.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "Video is already processing")
    if caption is not None:
        video.caption = caption
    video.status, video.error = "uploaded", ""
    db.commit()
    enqueue_video(video.id, background)
    return _out(video)


@router.post("/{video_id}/file", response_model=VideoOut, status_code=status.HTTP_202_ACCEPTED)
def attach_file(video_id: int, background: BackgroundTasks, file: UploadFile = File(...),
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Give a shared link its video file (saved from TikTok) when Reelish couldn't download it.
    The same recipe is read again, now watching and listening to the video."""
    video = _owned(db, video_id, user)
    if video.status == "processing":
        raise HTTPException(status.HTTP_409_CONFLICT, "Video is already processing")
    try:
        key = storage.save(_chunks(file), file.filename or "", settings.max_upload_mb * 1024 * 1024)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if video.storage_key:
        storage.delete(video.storage_key)
    video.storage_key, video.original_filename = key, (file.filename or "")[:255]
    video.status, video.error = "uploaded", ""
    db.commit()
    enqueue_video(video.id, background)
    return _out(video)


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    video = _owned(db, video_id, user)
    if video.storage_key:
        storage.delete(video.storage_key)
    db.delete(video)  # its recipe stays; recipe.video_id becomes NULL
    db.commit()
