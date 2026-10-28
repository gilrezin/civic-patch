from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_token, get_current_user, hash_password, verify_password
from ..db import get_db
from ..models import User
from ..schemas import AuthOut, LoginIn, SignupIn, UserOut
from ..services.edits import http_error

router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{2,32}$")


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, display_name=u.display_name)


@router.post("/signup", response_model=AuthOut, status_code=201)
def signup(body: SignupIn, db: Session = Depends(get_db)) -> AuthOut:
    email = body.email.strip().lower()
    name = body.display_name.strip()
    if not _EMAIL_RE.match(email):
        raise http_error(422, "email_invalid", "Please enter a valid email address.")
    if not _NAME_RE.match(name):
        raise http_error(422, "name_invalid", "Display names are 2-32 characters: letters, numbers, _ . or -")
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise http_error(409, "email_taken", "An account with that email already exists. Try signing in.")
    if db.execute(select(User).where(User.display_name == name)).scalar_one_or_none():
        raise http_error(409, "name_taken", "That display name is taken.")
    user = User(email=email, password_hash=hash_password(body.password), display_name=name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return AuthOut(token=create_token(user.id), user=_user_out(user))


@router.post("/login", response_model=AuthOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> AuthOut:
    email = body.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise http_error(401, "bad_credentials", "Email or password is incorrect.")
    return AuthOut(token=create_token(user.id), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)
