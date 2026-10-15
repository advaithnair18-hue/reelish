from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import create_token, current_user, hash_password, verify_password
from ..db import get_db
from ..models import User
from ..schemas import Credentials, ShareKeyOut, TokenOut, UserOut, UserPatch
from .shortcut import new_share_key

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with that email already exists")
    user = User(email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/login", response_model=TokenOut)
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    # Same message for unknown email and wrong password, so emails can't be probed.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    return TokenOut(access_token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_me(body: UserPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(user, field, value)
    db.commit()
    return user


@router.post("/share-key", response_model=ShareKeyOut)
def create_share_key(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Make a new key for the iPhone shortcut. Replaces any old key, which stops working."""
    key = new_share_key(user)
    db.commit()
    return ShareKeyOut(key=key, hint=user.share_key_hint)


@router.delete("/share-key", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_key(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.share_key_hash, user.share_key_hint, user.share_key_created_at = None, "", None
    db.commit()
