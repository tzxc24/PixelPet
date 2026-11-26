"""Authenticated controls use the existing PixelPet access middleware."""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from backend.devices.home import AlarmInput, LampInput, TRACKS

router = APIRouter(prefix="/api/home")


class DeviceInput(BaseModel):
    device_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")


class LampCommand(DeviceInput, LampInput):
    pass


class PlayCommand(DeviceInput):
    track: str = "morning"


@router.get("")
def status(request: Request):
    return dict(request.app.state.home.snapshot(), tracks=[
        dict(id=key, name=value[0]) for key, value in TRACKS.items()])


@router.post("/lamp")
def lamp(value: LampCommand, request: Request):
    return request.app.state.home.lamp(value.device_id, value.model_dump(exclude={"device_id"}))


@router.post("/play")
def play(value: PlayCommand, request: Request):
    if value.track not in TRACKS:
        raise HTTPException(422, "请选择已有音乐。")
    request.app.state.home.queue(value.device_id, value.track)
    return {"queued": True}


@router.post("/stop")
def stop(value: DeviceInput, request: Request):
    request.app.state.home.stop(value.device_id)
    return {"stopped": True}


@router.post("/alarms", status_code=201)
def create(value: AlarmInput, request: Request):
    try:
        return request.app.state.home.create(value)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.delete("/alarms/{identity}")
def delete(identity: str, request: Request):
    if not request.app.state.home.delete(identity):
        raise HTTPException(404, "定时不存在。")
    return {"deleted": True}
