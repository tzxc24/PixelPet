"""Typed business events; audit deliberately stores metadata only."""
from collections import deque
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator
import json
import math

EventType = Literal['touch.touch_down','touch.touch_up','touch.tap','touch.double_tap','touch.long_press','pet.state','pet.emotion','audio.record_start','audio.record_stop','audio.speak_start','audio.speak_end','haptic.pattern','haptic.pulse','device.connected','device.disconnected','device.error','clock.tick']

class Event(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Literal[1] = 1
    event_id: str = Field(default_factory=lambda: str(uuid4()), max_length=128)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    device_id: str = Field(default='pixelpet-sim-001', max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    type: EventType
    payload: dict = Field(default_factory=dict)

    @field_validator('payload')
    @classmethod
    def bounded_payload(cls,value):
        try:
            if len(json.dumps(value,allow_nan=False).encode())>16384:
                raise ValueError('event payload too large')
            for key in ('duration_ms','strength'):
                if key in value:
                    number=float(value[key])
                    if not math.isfinite(number): raise ValueError('invalid numeric payload')
        except (TypeError,OverflowError) as exc:
            raise ValueError('invalid payload') from exc
        return value

class EventBus:
    def __init__(self, capacity=256):
        self._audit = deque(maxlen=max(1,min(int(capacity),2048)))
        self.count = 0
        self._subscribers = []

    def publish(self,event):
        event = Event.model_validate(event) if isinstance(event,dict) else event
        self.count += 1
        self._audit.append({'event_id':event.event_id,'timestamp':event.timestamp.isoformat(),'device_id':event.device_id,'type':event.type})
        for subscriber in tuple(self._subscribers):
            subscriber(event)
        return event

    def history(self):
        return list(self._audit)

    def subscribe(self,callback):
        self._subscribers.append(callback)
        def unsubscribe():
            if callback in self._subscribers: self._subscribers.remove(callback)
        return unsubscribe
