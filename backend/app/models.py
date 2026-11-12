"""Database tables: users, edits, edit versions, votes, comments."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Store naive UTC in SQLite, always hand back timezone-aware UTC.

    SQLite drops tzinfo, so without this the API would emit timestamps with no offset and
    browsers would read them as local time (making every edit look like it was created in
    the future, hence a permanent "just now").
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Edit(Base):
    """One polygon region on the map. Its imagery is a chain of EditVersions."""

    __tablename__ = "edits"
    # sqlite_autoincrement: never reuse an id after a delete (ids are part of image URLs and
    # map feature state).
    __table_args__ = (
        CheckConstraint("status IN ('pending','done','failed')", name="ck_edit_status"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "polygon": polygon_geojson is the drawn shape. "highlight": polygon_geojson is the bbox of
    # the strokes stored in region_json, and the mask follows the strokes.
    kind: Mapped[str] = mapped_column(String(16), default="polygon", nullable=False)
    region_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    polygon_geojson: Mapped[str] = mapped_column(Text, nullable=False)
    bounds_w: Mapped[float] = mapped_column(Float, nullable=False)
    bounds_s: Mapped[float] = mapped_column(Float, nullable=False)
    bounds_e: Mapped[float] = mapped_column(Float, nullable=False)
    bounds_n: Mapped[float] = mapped_column(Float, nullable=False)
    zoom: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_x0: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_y0: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_x1: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_y1: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_w: Mapped[int] = mapped_column(Integer, nullable=False)
    crop_h: Mapped[int] = mapped_column(Integer, nullable=False)
    polygon_px_json: Mapped[str] = mapped_column(Text, nullable=False)
    scale: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    aspect_name: Mapped[str] = mapped_column(String(8), nullable=False)
    original_path: Mapped[str] = mapped_column(String(255), nullable=False)
    mask_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    place_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    municipality: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. "Philadelphia-PA"
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )

    creator: Mapped[User] = relationship("User", lazy="joined")
    versions: Mapped[list[EditVersion]] = relationship(
        "EditVersion", back_populates="edit", cascade="all, delete-orphan", order_by="EditVersion.version_number"
    )

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.bounds_w, self.bounds_s, self.bounds_e, self.bounds_n)


class EditVersion(Base):
    __tablename__ = "edit_versions"
    __table_args__ = (
        UniqueConstraint("edit_id", "version_number", name="uq_edit_version"),
        CheckConstraint("status IN ('pending','done','failed')", name="ck_version_status"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edit_id: Mapped[int] = mapped_column(ForeignKey("edits.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(String(300), nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("edit_versions.id", ondelete="SET NULL"), nullable=True
    )
    full_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    overlay_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    edit: Mapped[Edit] = relationship("Edit", back_populates="versions")
    creator: Mapped[User] = relationship("User", lazy="joined")


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (CheckConstraint("value IN (-1, 1)", name="ck_vote_value"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    edit_id: Mapped[int] = mapped_column(ForeignKey("edits.id", ondelete="CASCADE"), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class OsmCellCache(Base):
    """Processed OpenStreetMap features for one smart-select cell, kept across restarts."""

    __tablename__ = "osm_cells"

    ix: Mapped[int] = mapped_column(Integer, primary_key=True)
    iy: Mapped[int] = mapped_column(Integer, primary_key=True)
    fetched_at: Mapped[float] = mapped_column(Float, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)


class Bookmark(Base):
    """Private per-user saved posts."""

    __tablename__ = "bookmarks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    edit_id: Mapped[int] = mapped_column(ForeignKey("edits.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    edit_id: Mapped[int] = mapped_column(ForeignKey("edits.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)

    author: Mapped[User] = relationship("User", lazy="joined")
