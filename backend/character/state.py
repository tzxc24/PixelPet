"""Explicit animation states; these are previews, not AI emotion detection."""
from enum import Enum

from pydantic import BaseModel


class PetState(str, Enum):
    IDLE = "IDLE"
    HAPPY = "HAPPY"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    SHY = "SHY"
    SLEEP = "SLEEP"
    SURPRISED = "SURPRISED"
    ANNOYED = "ANNOYED"
    ERROR = "ERROR"


EMOTIONS = {
    PetState.IDLE: "normal", PetState.HAPPY: "happy", PetState.LISTENING: "curious",
    PetState.THINKING: "thinking", PetState.SPEAKING: "happy", PetState.SHY: "shy",
    PetState.SLEEP: "sleepy", PetState.SURPRISED: "surprised", PetState.ANNOYED: "angry", PetState.ERROR: "sad",
}


class PetSnapshot(BaseModel):
    state: PetState = PetState.IDLE
    emotion: str = "normal"
    recording: bool = False
    wifi_connected: bool = False
    ble_connected: bool = False
    last_event: str | None = None
