"""Validate all model-controlled data before persistence or animation dispatch."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Emotion = Literal["normal", "happy", "shy", "sad", "angry", "curious", "thinking", "sleepy", "surprised"]
Action = Literal["idle", "blink", "jump", "listen", "think", "speak", "sleep", "shake"]
Category = Literal["basic", "interest", "work", "project", "event", "preference", "explicit"]


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category = "explicit"
    content: str = Field(min_length=1, max_length=1000)
    importance: float = Field(default=.8, ge=0, le=1)

    @field_validator("content")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("content must not be blank")
        return value.strip()


class ModelReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str = Field(min_length=1, max_length=6000)
    emotion: Emotion
    action: Action
    dialog_state: Literal['active','standby'] = 'active'
    memories: list[MemoryInput] = Field(default_factory=list, max_length=8)

    @field_validator("reply")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("reply must not be blank")
        return value.strip()
