"""Initial schema for future user-scoped conversations and explicit memories."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profile"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), default="主人")
    profile_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    title: Mapped[str] = mapped_column(String(100), default="新对话", server_default="新对话")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    emotion: Mapped[str] = mapped_column(String(20), default="normal", server_default="normal")
    action: Mapped[str] = mapped_column(String(20), default="idle", server_default="idle")
    status: Mapped[str] = mapped_column(String(20), default="complete", server_default="complete")
    mode: Mapped[str] = mapped_column(String(20), default="legacy", server_default="legacy")


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (UniqueConstraint("user_id", "category", "memory_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.id"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    memory_key: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    importance: Mapped[float] = mapped_column(Float, default=.8, server_default="0.8")
    source: Mapped[str] = mapped_column(Text, default="manual", server_default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=now)
    confirmed: Mapped[bool] = mapped_column(Boolean,default=False,server_default="0")
    confidence: Mapped[float] = mapped_column(Float,default=.9,server_default="0.9")


class PetSetting(Base):
    __tablename__ = "pet_settings"
    __table_args__ = (UniqueConstraint("user_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user_profile.id"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
