"""Thread-safe local event adapter, replaceable without changing AI/storage."""
from enum import Enum
from threading import RLock
from typing import Protocol

from backend.character.state import EMOTIONS, PetSnapshot, PetState


class HardwareEvent(str, Enum):
    TOUCH_START = "touch_start"
    TOUCH_END = "touch_end"
    AUDIO_START = "audio_start"
    AUDIO_END = "audio_end"
    AUDIO_PLAY = "audio_play"
    WIFI_CONNECTED = "wifi_connected"
    BLE_CONNECTED = "ble_connected"


class HardwareAdapter(Protocol):
    def snapshot(self) -> PetSnapshot: ...
    def handle(self, event: HardwareEvent) -> PetSnapshot: ...
    def preview(self, state: PetState) -> PetSnapshot: ...


class HardwareSimulator:
    def __init__(self):
        self._state = PetSnapshot()
        self._lock = RLock()

    def snapshot(self) -> PetSnapshot:
        with self._lock:
            return self._state.model_copy(deep=True)

    def _set_animation(self, state: PetState):
        self._state.state = state
        self._state.emotion = EMOTIONS[state]

    def preview(self, state: PetState) -> PetSnapshot:
        with self._lock:
            self._set_animation(state)
            self._state.last_event = "preview"
            return self.snapshot()

    def handle(self, event: HardwareEvent) -> PetSnapshot:
        with self._lock:
            animations = {
                HardwareEvent.TOUCH_START: PetState.HAPPY,
                HardwareEvent.TOUCH_END: PetState.IDLE,
                HardwareEvent.AUDIO_START: PetState.LISTENING,
                HardwareEvent.AUDIO_END: PetState.THINKING,
                HardwareEvent.AUDIO_PLAY: PetState.SPEAKING,
            }
            if event in animations:
                self._set_animation(animations[event])
            if event == HardwareEvent.AUDIO_START:
                self._state.recording = True
            elif event in (HardwareEvent.AUDIO_END, HardwareEvent.AUDIO_PLAY):
                self._state.recording = False
            elif event == HardwareEvent.WIFI_CONNECTED:
                self._state.wifi_connected = True
            elif event == HardwareEvent.BLE_CONNECTED:
                self._state.ble_connected = True
            self._state.last_event = event.value
            return self.snapshot()
