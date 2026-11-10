"""Validated local-only simulation endpoints."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.character.state import PetSnapshot, PetState
from backend.hardware.simulator import HardwareEvent

router = APIRouter(prefix="/api")


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event: HardwareEvent


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: PetState


@router.get("/health")
def health(request: Request):
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={
            "status": "degraded", "database": "unavailable", "mode": "simulator", "phase": 1
        })
    return {"status": "ok", "database": "ok", "mode": "simulator", "phase": 1}


@router.get("/pet/state", response_model=PetSnapshot)
def pet_state(request: Request):
    return request.app.state.hardware.snapshot()


@router.post("/simulator/events", response_model=PetSnapshot)
def simulate_event(payload: EventInput, request: Request):
    snapshot=request.app.state.hardware.handle(payload.event)
    # Legacy buttons remain simulations; log metadata through the shared event bus
    # without pretending that a microphone/player/device was actually activated.
    bus=getattr(request.app.state,'event_bus',None)
    if bus is not None:
        from backend.events import Event
        mapping={'touch_start':'touch.tap','touch_end':'pet.state','audio_start':'audio.record_start','audio_end':'audio.record_stop','audio_play':'audio.speak_start','wifi_connected':'device.connected','ble_connected':'device.connected'}
        bus.publish(Event(type=mapping[payload.event.value],device_id='pixelpet-sim-001',payload={'simulated':True}))
    return snapshot


@router.post("/simulator/preview", response_model=PetSnapshot)
def preview_state(payload: PreviewInput, request: Request):
    return request.app.state.hardware.preview(payload.state)
